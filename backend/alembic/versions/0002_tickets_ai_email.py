"""tickets, AI, and email ingestion schema

Revision ID: 0002_tickets_ai_email
Revises: 0001_auth_initial
Create Date: 2026-05-13
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_tickets_ai_email"
down_revision: Union[str, None] = "0001_auth_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # ticket_categories
    # ------------------------------------------------------------------
    op.create_table(
        "ticket_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("banking_domain", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_categories_code", "ticket_categories", ["code"], unique=True)
    op.create_index("ix_ticket_categories_is_active", "ticket_categories", ["is_active"])

    # ------------------------------------------------------------------
    # ticket_subcategories
    # ------------------------------------------------------------------
    op.create_table(
        "ticket_subcategories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=False, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_subcategories_category_id", "ticket_subcategories", ["category_id"])

    # ------------------------------------------------------------------
    # sla_policies  (needed before tickets due to FK)
    # ------------------------------------------------------------------
    op.create_table(
        "sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("response_minutes", sa.Integer, nullable=False),
        sa.Column("resolution_minutes", sa.Integer, nullable=False),
        sa.Column("business_hours_only", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sla_policies_category_id", "sla_policies", ["category_id"])
    op.create_index("ix_sla_policies_priority", "sla_policies", ["priority"])

    # ------------------------------------------------------------------
    # tickets
    # ------------------------------------------------------------------
    op.create_table(
        "tickets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_number", sa.String(20), nullable=False, unique=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),

        # status / priority / source enums stored as varchar (not native PG enum)
        # to allow easy migration without ALTER TYPE
        sa.Column("status", sa.Enum(
            "new", "acknowledged", "assigned", "in_progress", "on_hold",
            "escalated", "resolved", "closed", "reopened",
            name="ticketstatus",
        ), nullable=False, server_default="new"),
        sa.Column("priority", sa.Enum(
            "critical", "high", "medium", "low",
            name="ticketpriority",
        ), nullable=False, server_default="medium"),
        sa.Column("source", sa.Enum(
            "email", "portal", "phone", "chat", "api",
            name="ticketsource",
        ), nullable=False, server_default="portal"),

        # Categorisation
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("subcategory_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_subcategories.id", ondelete="SET NULL"), nullable=True),

        # People
        sa.Column("reporter_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),

        # Branch / department
        sa.Column("branch_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("branches.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),

        # Tags (PostgreSQL ARRAY)
        sa.Column("tags", postgresql.ARRAY(sa.String), nullable=True),

        # AI enrichment
        sa.Column("ai_category", sa.String(50), nullable=True),
        sa.Column("ai_subcategory", sa.String(50), nullable=True),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("ai_summary", sa.Text, nullable=True),
        sa.Column("ai_risk_score", sa.Float, nullable=True),
        sa.Column("ai_routing_reason", sa.String(500), nullable=True),
        sa.Column("ai_sentiment", sa.String(20), nullable=True),

        # Email threading
        sa.Column("email_message_id", sa.String(255), nullable=True),
        sa.Column("email_from", sa.String(255), nullable=True),
        sa.Column("email_subject", sa.String(500), nullable=True),

        # SLA
        sa.Column("sla_policy_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sla_breached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("sla_paused_at", sa.DateTime(timezone=True), nullable=True),

        # Timestamps
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),

        # Duplicate detection
        sa.Column("duplicate_of_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_duplicate", sa.Boolean, nullable=False, server_default=sa.false()),

        # Internal notes
        sa.Column("internal_notes", sa.Text, nullable=True),

        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_tickets_ticket_number", "tickets", ["ticket_number"], unique=True)
    op.create_index("ix_tickets_status", "tickets", ["status"])
    op.create_index("ix_tickets_priority", "tickets", ["priority"])
    op.create_index("ix_tickets_reporter_id", "tickets", ["reporter_id"])
    op.create_index("ix_tickets_assignee_id", "tickets", ["assignee_id"])
    op.create_index("ix_tickets_branch_id", "tickets", ["branch_id"])
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"])
    op.create_index("ix_tickets_email_message_id", "tickets", ["email_message_id"])
    op.create_index("ix_tickets_category_id", "tickets", ["category_id"])
    op.create_index("ix_tickets_sla_breached", "tickets", ["sla_breached"])

    # ------------------------------------------------------------------
    # ticket_comments
    # ------------------------------------------------------------------
    op.create_table(
        "ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_internal", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("source", sa.Enum(
            "email", "agent", "ai", "system",
            name="commentsource",
        ), nullable=False, server_default="agent"),
        sa.Column("ai_generated", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])
    op.create_index("ix_ticket_comments_author_id", "ticket_comments", ["author_id"])

    # ------------------------------------------------------------------
    # attachments
    # ------------------------------------------------------------------
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploader_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False, unique=True),
        sa.Column("s3_bucket", sa.String(100), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("is_malware_scanned", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_clean", sa.Boolean, nullable=True),
        sa.Column("has_pii_detected", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ocr_text", sa.Text, nullable=True),
        sa.Column("document_type", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])
    op.create_index("ix_attachments_s3_key", "attachments", ["s3_key"], unique=True)

    # ------------------------------------------------------------------
    # sla_tracking
    # ------------------------------------------------------------------
    op.create_table(
        "sla_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sla_policies.id", ondelete="SET NULL"), nullable=True),
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_response_breached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_resolution_breached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_paused_minutes", sa.Integer, nullable=False, server_default="0"),
        sa.Column("breach_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("ticket_id", name="uq_sla_tracking_ticket"),
    )
    op.create_index("ix_sla_tracking_ticket_id", "sla_tracking", ["ticket_id"])
    op.create_index("ix_sla_tracking_is_resolution_breached", "sla_tracking", ["is_resolution_breached"])
    op.create_index("ix_sla_tracking_resolution_due_at", "sla_tracking", ["resolution_due_at"])

    # ------------------------------------------------------------------
    # escalation_rules
    # ------------------------------------------------------------------
    op.create_table(
        "escalation_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger", sa.Enum(
            "sla_breach", "manual", "high_risk", "vip_customer", "regulatory",
            name="escalationtrigger",
        ), nullable=False),
        sa.Column("trigger_after_minutes", sa.Integer, nullable=True),
        sa.Column("escalate_to_role", sa.String(50), nullable=False),
        sa.Column("escalate_to_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notify_email", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("priority_threshold", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_escalation_rules_category_id", "escalation_rules", ["category_id"])
    op.create_index("ix_escalation_rules_is_active", "escalation_rules", ["is_active"])

    # ------------------------------------------------------------------
    # escalation_events
    # ------------------------------------------------------------------
    op.create_table(
        "escalation_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("escalation_rules.id", ondelete="SET NULL"), nullable=True),
        sa.Column("trigger", sa.Enum(
            "sla_breach", "manual", "high_risk", "vip_customer", "regulatory",
            name="escalationtrigger",
            create_type=False,  # already created above
        ), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("escalated_to_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("escalated_by_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_escalation_events_ticket_id", "escalation_events", ["ticket_id"])
    op.create_index("ix_escalation_events_triggered_at", "escalation_events", ["triggered_at"])

    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=True),
        sa.Column("action", sa.Enum(
            "create", "update", "delete", "view", "export",
            "login", "logout", "status_change", "assignment",
            "escalation", "ai_decision",
            name="auditaction",
        ), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("old_values", postgresql.JSON, nullable=True),
        sa.Column("new_values", postgresql.JSON, nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("metadata", postgresql.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # ------------------------------------------------------------------
    # inbound_emails
    # ------------------------------------------------------------------
    op.create_table(
        "inbound_emails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("message_id", sa.String(255), nullable=False, unique=True),
        sa.Column("from_address", sa.String(255), nullable=False),
        sa.Column("from_name", sa.String(255), nullable=True),
        sa.Column("to_address", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("in_reply_to", sa.String(255), nullable=True),
        sa.Column("body_text", sa.Text, nullable=True),
        sa.Column("body_html", sa.Text, nullable=True),
        sa.Column("raw_payload", sa.Text, nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_processed", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_error", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_inbound_emails_message_id", "inbound_emails", ["message_id"], unique=True)
    op.create_index("ix_inbound_emails_processed", "inbound_emails", ["is_processed"])
    op.create_index("ix_inbound_emails_received_at", "inbound_emails", ["received_at"])
    op.create_index("ix_inbound_emails_ticket_id", "inbound_emails", ["ticket_id"])

    # ------------------------------------------------------------------
    # chat_sessions
    # ------------------------------------------------------------------
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_ticket_id", "chat_sessions", ["ticket_id"])

    # ------------------------------------------------------------------
    # chat_messages
    # ------------------------------------------------------------------
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.Enum(
            "user", "assistant", "system",
            name="chatrole",
        ), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # ------------------------------------------------------------------
    # ai_interaction_logs
    # ------------------------------------------------------------------
    op.create_table(
        "ai_interaction_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("interaction_type", sa.String(50), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("success", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("result", postgresql.JSON, nullable=True),
        sa.Column("confidence_score", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_interaction_logs_ticket_id", "ai_interaction_logs", ["ticket_id"])
    op.create_index("ix_ai_interaction_logs_user_id", "ai_interaction_logs", ["user_id"])
    op.create_index("ix_ai_interaction_logs_interaction_type", "ai_interaction_logs", ["interaction_type"])
    op.create_index("ix_ai_interaction_logs_created_at", "ai_interaction_logs", ["created_at"])

    # ------------------------------------------------------------------
    # Seed data — default ticket categories and subcategories
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO ticket_categories (id, code, name, department, banking_domain, description, is_active)
        VALUES
          (gen_random_uuid(), 'payments',    'Payments',           'Operations',  'retail',     'Payment and transaction related issues',          true),
          (gen_random_uuid(), 'fraud',       'Fraud & Disputes',   'Risk',        'risk',       'Fraud detection and transaction disputes',        true),
          (gen_random_uuid(), 'kyc',         'KYC & Onboarding',   'Compliance',  'compliance', 'Customer verification and account onboarding',   true),
          (gen_random_uuid(), 'loans',       'Loans & Credit',     'Lending',     'lending',    'Loan applications and EMI management',            true),
          (gen_random_uuid(), 'compliance',  'Compliance',         'Compliance',  'compliance', 'Regulatory and compliance related queries',       true),
          (gen_random_uuid(), 'it',          'IT Support',         'IT',          'internal',   'System access and software issues',               true),
          (gen_random_uuid(), 'operations',  'Branch Operations',  'Operations',  'retail',     'Branch and cash management operations',           true)
    """)

    # Seed subcategories
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'upi_payments', 'UPI Payments', 'UPI transaction failures and disputes', true
        FROM ticket_categories c WHERE c.code = 'payments'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'neft_rtgs', 'NEFT / RTGS', 'NEFT and RTGS fund transfer issues', true
        FROM ticket_categories c WHERE c.code = 'payments'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'card_payments', 'Card Payments', 'Debit and credit card payment issues', true
        FROM ticket_categories c WHERE c.code = 'payments'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'account_fraud', 'Account Fraud', 'Unauthorized account access and fraud', true
        FROM ticket_categories c WHERE c.code = 'fraud'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'txn_dispute', 'Transaction Dispute', 'Customer transaction disputes and chargebacks', true
        FROM ticket_categories c WHERE c.code = 'fraud'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'kyc_verification', 'KYC Verification', 'Identity document verification', true
        FROM ticket_categories c WHERE c.code = 'kyc'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'onboarding', 'Onboarding', 'New customer account opening', true
        FROM ticket_categories c WHERE c.code = 'kyc'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'loan_application', 'Loan Application', 'New loan application processing', true
        FROM ticket_categories c WHERE c.code = 'loans'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'emi_issues', 'EMI Issues', 'EMI payment failures and reschedule requests', true
        FROM ticket_categories c WHERE c.code = 'loans'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'regulatory_compliance', 'Regulatory Compliance', 'RBI and regulatory compliance queries', true
        FROM ticket_categories c WHERE c.code = 'compliance'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'audit_queries', 'Audit Queries', 'Internal and external audit queries', true
        FROM ticket_categories c WHERE c.code = 'compliance'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'system_access', 'System Access', 'User access provisioning and password resets', true
        FROM ticket_categories c WHERE c.code = 'it'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'software_issues', 'Software Issues', 'Core banking and application issues', true
        FROM ticket_categories c WHERE c.code = 'it'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'branch_ops', 'Branch Operations', 'Day-to-day branch operational issues', true
        FROM ticket_categories c WHERE c.code = 'operations'
    """)
    op.execute("""
        INSERT INTO ticket_subcategories (id, category_id, code, name, description, is_active)
        SELECT gen_random_uuid(), c.id, 'cash_management', 'Cash Management', 'Vault, ATM and cash management', true
        FROM ticket_categories c WHERE c.code = 'operations'
    """)

    # ------------------------------------------------------------------
    # Seed data — default SLA policies (global, no category binding)
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO sla_policies (id, name, category_id, priority, response_minutes, resolution_minutes, business_hours_only, is_default)
        VALUES
          (gen_random_uuid(), 'Default CRITICAL SLA', NULL, 'critical', 30,   120,  false, true),
          (gen_random_uuid(), 'Default HIGH SLA',     NULL, 'high',     60,   360,  false, true),
          (gen_random_uuid(), 'Default MEDIUM SLA',   NULL, 'medium',   240,  1440, false, true),
          (gen_random_uuid(), 'Default LOW SLA',      NULL, 'low',      480,  4320, false, true)
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("ai_interaction_logs")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("inbound_emails")
    op.drop_table("audit_logs")
    op.drop_table("escalation_events")
    op.drop_table("escalation_rules")
    op.drop_table("sla_tracking")
    op.drop_table("attachments")
    op.drop_table("ticket_comments")
    op.drop_table("tickets")
    op.drop_table("sla_policies")
    op.drop_table("ticket_subcategories")
    op.drop_table("ticket_categories")

    # Drop custom enum types
    op.execute("DROP TYPE IF EXISTS chatrole")
    op.execute("DROP TYPE IF EXISTS auditaction")
    op.execute("DROP TYPE IF EXISTS escalationtrigger")
    op.execute("DROP TYPE IF EXISTS commentsource")
    op.execute("DROP TYPE IF EXISTS ticketsource")
    op.execute("DROP TYPE IF EXISTS ticketpriority")
    op.execute("DROP TYPE IF EXISTS ticketstatus")
