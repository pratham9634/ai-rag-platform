"""
Celery Distributed Task Queue Application Configuration.

Configures RabbitMQ AMQP broker, Redis result store, durable task queues,
fair worker prefetch, and RabbitMQ Dead-Letter Queue (DLQ) integration.
"""

import logging

from celery import Celery
from kombu import Exchange, Queue

from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Celery app instance
celery_app = Celery(
    "enterprise_rag_tasks",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.ingestion_tasks"],
)

# AMQP Exchanges and Queues with Dead-Letter routing
default_exchange = Exchange("documents.exchange", type="direct", durable=True)
dlx_exchange = Exchange("documents.dlx", type="direct", durable=True)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Worker safety: Acknowledge only after successful completion
    task_acks_late=True,
    # Fair worker scheduling for CPU-intensive embedding workloads
    worker_prefetch_multiplier=1,
    # Durable queues + DLQ binding
    task_queues=(
        Queue(
            "documents.ingestion",
            default_exchange,
            routing_key="documents.ingestion",
            queue_arguments={
                "x-dead-letter-exchange": "documents.dlx",
                "x-dead-letter-routing-key": "documents.dlq",
            },
        ),
        Queue(
            "documents.dlq",
            dlx_exchange,
            routing_key="documents.dlq",
        ),
    ),
    task_default_queue="documents.ingestion",
    task_default_exchange="documents.exchange",
    task_default_routing_key="documents.ingestion",
    task_routes={
        "tasks.ingest_document": {"queue": "documents.ingestion"},
    },
)
