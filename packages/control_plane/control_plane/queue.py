QUEUE_NAME = "jobs:queue:v1"
JOB_LOG_CHANNEL_PREFIX = "jobs:log:v1:"


def job_log_channel(job_id: str) -> str:
    return f"{JOB_LOG_CHANNEL_PREFIX}{job_id}"

