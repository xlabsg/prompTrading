import os
import shutil
import tempfile
import time
import unittest

from control_plane.file_queue import FileJobQueue, INTERACTIVE_PRIORITY, BATCH_PRIORITY
from control_plane.queue import enqueue_job, get_file_queue, request_cancel_job, is_job_cancelled


class TestFileJobQueue(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_file_queue_priority_and_fifo(self):
        q = FileJobQueue(self.temp_dir)

        # Enqueue a batch job first
        q.enqueue(job_id="batch-1", job_type="trending_scrape")
        time.sleep(0.01)

        # Enqueue interactive jobs
        q.enqueue(job_id="interactive-1", job_type="generate_and_backtest")
        time.sleep(0.01)
        q.enqueue(job_id="interactive-2", job_type="backtest")
        time.sleep(0.01)
        q.enqueue(job_id="batch-2", job_type="template_performance_update")

        # Dequeue 1: should get interactive-1
        item1 = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item1)
        self.assertEqual(item1.job_id, "interactive-1")
        self.assertEqual(item1.priority, INTERACTIVE_PRIORITY)
        q.mark_completed(item1)

        # Dequeue 2: should get interactive-2
        item2 = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item2)
        self.assertEqual(item2.job_id, "interactive-2")
        self.assertEqual(item2.priority, INTERACTIVE_PRIORITY)
        q.mark_completed(item2)

        # Dequeue 3: interactive empty -> should get batch-1
        item3 = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item3)
        self.assertEqual(item3.job_id, "batch-1")
        self.assertEqual(item3.priority, BATCH_PRIORITY)
        q.mark_completed(item3)

        # Dequeue 4: should get batch-2
        item4 = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item4)
        self.assertEqual(item4.job_id, "batch-2")
        self.assertEqual(item4.priority, BATCH_PRIORITY)
        q.mark_completed(item4)

        # Dequeue 5: empty
        item5 = q.dequeue(timeout_s=0.05)
        self.assertIsNone(item5)

    def test_cancellation(self):
        workspaces = self.temp_dir
        self.assertFalse(is_job_cancelled(workspaces, "job-123"))
        request_cancel_job(workspaces, "job-123")
        self.assertTrue(is_job_cancelled(workspaces, "job-123"))

        q = get_file_queue(workspaces)
        q.clear_cancel("job-123")
        self.assertFalse(is_job_cancelled(workspaces, "job-123"))

    def test_recovery(self):
        q = FileJobQueue(self.temp_dir)
        q.enqueue(job_id="crash-job", job_type="backtest")
        item = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item)
        self.assertEqual(item.job_id, "crash-job")

        # Simulate crash before completion, then new worker starts and recovers
        recovered = q.recover_stale_processing_jobs()
        self.assertEqual(recovered, 1)

        item_again = q.dequeue(timeout_s=0.1)
        self.assertIsNotNone(item_again)
        self.assertEqual(item_again.job_id, "crash-job")
        q.mark_completed(item_again)


if __name__ == "__main__":
    unittest.main()
