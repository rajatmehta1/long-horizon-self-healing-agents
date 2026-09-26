import asyncio
import logging

from temporalio.worker import Worker

from app.activities import ingest_complaint, assess_eligibility, process_refund, notify_policy_rejection, \
    send_customer_response
from app.contracts import TEMPORAL_HOST, TEMPORAL_TASK_QUEUE
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
import concurrent.futures
from app.workflow import CustomerSupportWorkflow

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

async def _run() -> None:
    client = await Client.connect(TEMPORAL_HOST, data_converter=pydantic_data_converter)
    async with Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[CustomerSupportWorkflow],
        activities=[
            ingest_complaint,
            assess_eligibility,
            process_refund,
            notify_policy_rejection,
            send_customer_response
        ],
        activity_executor=concurrent.futures.ThreadPoolExecutor(max_workers=10)
    ):
        print(f"n Worker started | task queue: {TEMPORAL_TASK_QUEUE}")
        print(f" Temporal UI | http://localhost:3001\n")
        await asyncio.Event().wait() #runt untilst cotn

if __name__ == '__main__':
    asyncio.run(_run())