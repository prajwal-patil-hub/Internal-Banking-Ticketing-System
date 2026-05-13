"""AI service — all Claude-powered operations for the banking ticketing system.

Uses the Anthropic SDK (synchronous client) wrapped in asyncio.run_in_executor
so it integrates cleanly with FastAPI's async request handlers.

All AI calls are logged to AIInteractionLog for auditability, cost tracking,
and replay/debugging.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import anthropic

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ai_interaction import AIInteractionLog
from app.schemas.ai import AICategorizationResult, AIEmailExtraction, AIResolutionSuggestion
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)


class AIService:
    MODEL = "claude-sonnet-4-6"

    def __init__(
        self,
        db: AsyncSession,
        actor_id: str | None = None,
    ) -> None:
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.db = db
        self.actor_id = actor_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_sync(self, func, *args, **kwargs):
        """Run a synchronous callable in a thread-pool executor."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(None, lambda: func(*args, **kwargs))

    def _create_message(
        self,
        messages: list[dict],
        *,
        system: str | None = None,
        max_tokens: int = 1024,
    ) -> anthropic.types.Message:
        """Synchronous Claude call — always call via _run_sync."""
        kwargs: dict[str, Any] = {
            "model": self.MODEL,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        return self.client.messages.create(**kwargs)

    def _parse_json_response(self, content: str) -> dict:
        """Strip markdown fences and parse JSON from model output."""
        text = content.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # drop first line (```json) and last line (```)
            text = "\n".join(lines[1:-1]) if len(lines) > 2 else text
        return json.loads(text)

    async def _log_interaction(
        self,
        action_type: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        latency_ms: int,
        confidence: float | None,
        entity_type: str | None,
        entity_id: str | None,
        success: bool = True,
        error: str | None = None,
        input_hash: str | None = None,
        output_summary: str | None = None,
    ) -> None:
        """Persist an AIInteractionLog row for every API call."""
        actor_uuid: uuid.UUID | None = None
        if self.actor_id:
            try:
                actor_uuid = uuid.UUID(self.actor_id)
            except ValueError:
                pass

        entry = AIInteractionLog(
            interaction_type=action_type,
            model_id=model,
            prompt_tokens=tokens_in,
            completion_tokens=tokens_out,
            latency_ms=latency_ms,
            success=success,
            error_message=error,
            confidence_score=confidence,
            user_id=actor_uuid,
            result={"output_summary": output_summary} if output_summary else None,
        )
        self.db.add(entry)
        try:
            await self.db.flush()
        except Exception as exc:
            log.warning("ai_log.flush_failed", error=str(exc))

    # ------------------------------------------------------------------
    # Categorization
    # ------------------------------------------------------------------

    async def categorize_ticket(
        self,
        title: str,
        description: str,
        source_email: str | None = None,
    ) -> AICategorizationResult:
        """Use Claude to categorize a banking support ticket."""
        prompt = f"""You are an expert banking operations analyst at SUCCESS Bank. Analyze this support ticket and provide structured categorization.

Banking domains: payments, fraud, kyc, loans, compliance, it, operations, treasury, dispute, reconciliation, access

Ticket Title: {title}
Ticket Description: {description[:2000]}
{f"From Email: {source_email}" if source_email else ""}

Respond in JSON with exactly these fields:
{{
  "category": "one of: payments|fraud|kyc|loans|compliance|it|operations|treasury|dispute|reconciliation|access",
  "subcategory": "specific subcategory within the main category",
  "priority": "one of: critical|high|medium|low",
  "confidence": 0.0-1.0,
  "risk_score": 0.0-1.0,
  "risk_factors": ["list of identified risk factors"],
  "department": "responsible department name",
  "sla_recommendation": "suggested SLA timeframe",
  "routing_reason": "brief explanation of why this routing was chosen",
  "requires_escalation": true/false,
  "is_regulatory": true/false,
  "sentiment": "positive|neutral|negative|urgent"
}}

Only output valid JSON. No markdown, no explanation."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()
        error_msg: str | None = None
        result_data: dict = {}

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=1024
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            raw_text = response.content[0].text
            result_data = self._parse_json_response(raw_text)
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            error_msg = str(exc)
            log.exception("ai.categorize_ticket.failed", error=error_msg)
            await self._log_interaction(
                "categorize", self.MODEL, 0, 0, latency_ms, None,
                "ticket", None, success=False, error=error_msg,
            )
            # Return a safe fallback
            return AICategorizationResult(
                category="operations",
                subcategory=None,
                priority="medium",
                confidence=0.0,
                risk_score=0.0,
                risk_factors=[],
                department="Operations",
                sla_recommendation="Standard SLA",
                routing_reason="AI categorization failed; default routing applied.",
                requires_escalation=False,
                is_regulatory=False,
                sentiment="neutral",
            )

        await self._log_interaction(
            "categorize",
            self.MODEL,
            tokens_in,
            tokens_out,
            latency_ms,
            result_data.get("confidence"),
            "ticket",
            None,
            success=True,
            output_summary=result_data.get("category"),
        )

        return AICategorizationResult(
            category=result_data.get("category", "operations"),
            subcategory=result_data.get("subcategory"),
            priority=result_data.get("priority", "medium"),
            confidence=float(result_data.get("confidence", 0.5)),
            risk_score=float(result_data.get("risk_score", 0.0)),
            risk_factors=result_data.get("risk_factors", []),
            department=result_data.get("department", "Operations"),
            sla_recommendation=result_data.get("sla_recommendation", "Standard SLA"),
            routing_reason=result_data.get("routing_reason", ""),
            requires_escalation=bool(result_data.get("requires_escalation", False)),
            is_regulatory=bool(result_data.get("is_regulatory", False)),
            sentiment=result_data.get("sentiment", "neutral"),
        )

    # ------------------------------------------------------------------
    # Email entity extraction
    # ------------------------------------------------------------------

    async def extract_email_entities(
        self,
        subject: str,
        body: str,
        from_address: str,
    ) -> AIEmailExtraction:
        """Extract banking entities and metadata from an inbound email."""
        prompt = f"""You are analyzing an inbound email to SUCCESS Bank's support system.

Email Subject: {subject}
From: {from_address}
Body: {body[:3000]}

Extract structured data for ticket creation. Respond in JSON:
{{
  "title": "concise ticket title (max 120 chars)",
  "summary": "2-3 sentence summary of the issue",
  "category": "payments|fraud|kyc|loans|compliance|it|operations|treasury|dispute|reconciliation|access",
  "priority": "critical|high|medium|low",
  "confidence": 0.0-1.0,
  "entities": {{
    "account_refs": ["any account numbers mentioned, partially masked"],
    "transaction_refs": ["any transaction IDs, UTR numbers, reference numbers"],
    "urgency_signals": ["phrases indicating urgency"]
  }},
  "risk_score": 0.0-1.0
}}

Only output valid JSON. No markdown, no explanation."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=1024
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            result_data = self._parse_json_response(response.content[0].text)
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.extract_email.failed", error=str(exc))
            await self._log_interaction(
                "extract_email", self.MODEL, 0, 0, latency_ms, None,
                "email", None, success=False, error=str(exc),
            )
            return AIEmailExtraction(
                title=subject[:120] if subject else "Inbound email",
                summary="Could not extract summary from email.",
                category="operations",
                priority="medium",
                confidence=0.0,
                entities={"account_refs": [], "transaction_refs": [], "urgency_signals": []},
                risk_score=0.0,
            )

        await self._log_interaction(
            "extract_email", self.MODEL, tokens_in, tokens_out, latency_ms,
            result_data.get("confidence"), "email", None, success=True,
            output_summary=result_data.get("title"),
        )

        entities = result_data.get("entities", {})
        return AIEmailExtraction(
            title=result_data.get("title", subject[:120] if subject else "Inbound email"),
            summary=result_data.get("summary", ""),
            category=result_data.get("category", "operations"),
            priority=result_data.get("priority", "medium"),
            confidence=float(result_data.get("confidence", 0.5)),
            entities={
                "account_refs": entities.get("account_refs", []),
                "transaction_refs": entities.get("transaction_refs", []),
                "urgency_signals": entities.get("urgency_signals", []),
            },
            risk_score=float(result_data.get("risk_score", 0.0)),
        )

    # ------------------------------------------------------------------
    # Summarize ticket
    # ------------------------------------------------------------------

    async def summarize_ticket(self, ticket_data: dict) -> str:
        """Generate a concise AI summary of a ticket and its comments."""
        title = ticket_data.get("title", "")
        description = ticket_data.get("description", "")
        status = ticket_data.get("status", "")
        comments = ticket_data.get("comments", [])

        comments_text = "\n".join(
            f"[{c.get('created_at', '')}] {c.get('author', 'Unknown')}: {c.get('body', '')[:300]}"
            for c in comments[:10]
        )

        prompt = f"""Summarize this banking support ticket for an agent in 3-4 sentences.
Include: core issue, current status, key actions taken, and recommended next step.

Title: {title}
Status: {status}
Description: {description[:1500]}

Recent comments:
{comments_text}

Write a concise summary only. No bullet points or headers."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=512
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            summary = response.content[0].text.strip()
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.summarize_ticket.failed", error=str(exc))
            await self._log_interaction(
                "summarize", self.MODEL, 0, 0, latency_ms, None,
                "ticket", ticket_data.get("id"), success=False, error=str(exc),
            )
            return "Summary unavailable."

        await self._log_interaction(
            "summarize", self.MODEL,
            response.usage.input_tokens, response.usage.output_tokens,
            latency_ms, None, "ticket", ticket_data.get("id"), success=True,
        )
        return summary

    # ------------------------------------------------------------------
    # Resolution suggestion
    # ------------------------------------------------------------------

    async def suggest_resolution(
        self,
        ticket: dict,
        similar_tickets: list[dict],
    ) -> AIResolutionSuggestion:
        """Suggest resolution steps based on the ticket and similar resolved tickets."""
        similar_text = "\n".join(
            f"- [{t.get('ticket_number', '')}] {t.get('title', '')}: resolved by {t.get('resolution_summary', 'N/A')}"
            for t in similar_tickets[:5]
        )

        prompt = f"""You are a banking support expert. Suggest a resolution for this ticket.

Current Ticket:
Title: {ticket.get('title', '')}
Category: {ticket.get('ai_category', ticket.get('category', 'unknown'))}
Description: {ticket.get('description', '')[:1000]}

Similar resolved tickets:
{similar_text if similar_text else "No similar tickets found."}

Respond in JSON:
{{
  "suggestion": "detailed step-by-step resolution recommendation",
  "confidence": 0.0-1.0,
  "similar_ticket_ids": ["list of relevant ticket numbers from similar tickets"],
  "knowledge_refs": ["relevant policy or KB references"]
}}

Only output valid JSON."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=1024
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            result_data = self._parse_json_response(response.content[0].text)
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.suggest_resolution.failed", error=str(exc))
            await self._log_interaction(
                "suggest_resolution", self.MODEL, 0, 0, latency_ms, None,
                "ticket", ticket.get("id"), success=False, error=str(exc),
            )
            return AIResolutionSuggestion(
                suggestion="Unable to generate resolution suggestion at this time.",
                confidence=0.0,
                similar_ticket_ids=[],
                knowledge_refs=[],
            )

        await self._log_interaction(
            "suggest_resolution", self.MODEL,
            response.usage.input_tokens, response.usage.output_tokens,
            latency_ms, result_data.get("confidence"), "ticket", ticket.get("id"),
        )

        return AIResolutionSuggestion(
            suggestion=result_data.get("suggestion", ""),
            confidence=float(result_data.get("confidence", 0.5)),
            similar_ticket_ids=result_data.get("similar_ticket_ids", []),
            knowledge_refs=result_data.get("knowledge_refs", []),
        )

    # ------------------------------------------------------------------
    # Response draft
    # ------------------------------------------------------------------

    async def generate_response_draft(self, ticket: dict) -> str:
        """Draft a professional customer-facing response for the ticket."""
        prompt = f"""You are a professional banking support representative at SUCCESS Bank.
Draft a polite, empathetic, and professional response to this customer support ticket.

Ticket: {ticket.get('ticket_number', '')}
Title: {ticket.get('title', '')}
Priority: {ticket.get('priority', 'medium')}
Description: {ticket.get('description', '')[:1000]}

Guidelines:
- Address the customer's concern directly
- Mention ticket number for reference
- Set realistic expectations for resolution timeframe
- Close professionally
- Do NOT reveal internal system details or SLA metrics
- Keep under 200 words

Write the email body only."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=512
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            draft = response.content[0].text.strip()
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.generate_response_draft.failed", error=str(exc))
            await self._log_interaction(
                "generate_response", self.MODEL, 0, 0, latency_ms, None,
                "ticket", ticket.get("id"), success=False, error=str(exc),
            )
            return (
                f"Dear Customer,\n\nThank you for contacting SUCCESS Bank support. "
                f"Your ticket ({ticket.get('ticket_number', 'N/A')}) has been received "
                f"and is being reviewed by our team. We will get back to you shortly.\n\n"
                f"Regards,\nSUCCESS Bank Support"
            )

        await self._log_interaction(
            "generate_response", self.MODEL,
            response.usage.input_tokens, response.usage.output_tokens,
            latency_ms, None, "ticket", ticket.get("id"),
        )
        return draft

    # ------------------------------------------------------------------
    # Sentiment / urgency detection
    # ------------------------------------------------------------------

    async def detect_sentiment_urgency(self, text: str) -> dict:
        """Detect sentiment and urgency signals in ticket text."""
        prompt = f"""Analyze the following banking support text for sentiment and urgency.

Text: {text[:1500]}

Respond in JSON:
{{
  "sentiment": "positive|neutral|negative|urgent",
  "urgency_level": "low|medium|high|critical",
  "urgency_signals": ["list of phrases indicating urgency"],
  "emotional_tone": "brief description",
  "confidence": 0.0-1.0
}}

Only output valid JSON."""

        messages = [{"role": "user", "content": prompt}]
        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message, messages, max_tokens=512
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            result_data = self._parse_json_response(response.content[0].text)
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.detect_sentiment.failed", error=str(exc))
            await self._log_interaction(
                "detect_sentiment", self.MODEL, 0, 0, latency_ms, None,
                None, None, success=False, error=str(exc),
            )
            return {"sentiment": "neutral", "urgency_level": "low", "urgency_signals": [], "confidence": 0.0}

        await self._log_interaction(
            "detect_sentiment", self.MODEL,
            response.usage.input_tokens, response.usage.output_tokens,
            latency_ms, result_data.get("confidence"), None, None,
        )
        return result_data

    # ------------------------------------------------------------------
    # Chat assistant
    # ------------------------------------------------------------------

    async def chat_with_assistant(
        self,
        message: str,
        session_history: list[dict],
        context: dict | None = None,
    ) -> tuple[str, int, int]:
        """
        Main AI chat assistant for banking staff.

        Returns (response_text, input_tokens, output_tokens).
        session_history is a list of {"role": "user"|"assistant", "content": str}.
        context can carry ticket/entity data to enrich the system prompt.
        """
        system_prompt = """You are an AI assistant for SUCCESS Bank's internal support system.
You help bank staff with:
- Creating and managing support tickets
- Understanding workflows and SOPs
- Looking up ticket information and status
- Providing SLA guidance
- Explaining compliance requirements
- Suggesting next steps for ticket resolution

Always be professional, concise, and banking-compliance aware.
Never reveal sensitive customer PII.
Always recommend human review for: fraud alerts, regulatory matters, amounts > ₹10 lakhs.
If you don't know something, say so clearly rather than guessing."""

        if context:
            context_lines = []
            for key, value in context.items():
                if value is not None:
                    context_lines.append(f"{key}: {value}")
            if context_lines:
                system_prompt += "\n\nCurrent context:\n" + "\n".join(context_lines)

        # Build conversation messages (cap history at last 20 turns)
        messages: list[dict] = []
        for turn in session_history[-20:]:
            role = turn.get("role", "user")
            content = turn.get("content", "")
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        start = time.monotonic()

        try:
            response: anthropic.types.Message = await self._run_sync(
                self._create_message,
                messages,
                system=system_prompt,
                max_tokens=2048,
            )
            latency_ms = int((time.monotonic() - start) * 1000)
            tokens_in = response.usage.input_tokens
            tokens_out = response.usage.output_tokens
            reply = response.content[0].text.strip()
        except Exception as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            log.exception("ai.chat.failed", error=str(exc))
            await self._log_interaction(
                "chat", self.MODEL, 0, 0, latency_ms, None,
                None, None, success=False, error=str(exc),
            )
            return (
                "I'm sorry, I'm having trouble responding right now. "
                "Please try again in a moment or contact your system administrator.",
                0,
                0,
            )

        await self._log_interaction(
            "chat", self.MODEL, tokens_in, tokens_out, latency_ms,
            None, None, None, success=True,
        )
        return reply, tokens_in, tokens_out
