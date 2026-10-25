from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class Job:
    title: str
    company: str
    location: str
    work_mode: str
    source: str
    source_url: str
    apply_url: str
    posted_at: str | None = None
    closing_at: str | None = None
    employer_verified: bool = False
    vacancy_confirmed: bool = False


def valid_https(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and bool(parsed.netloc)
    except (TypeError, ValueError):
        return False


def is_verified(job: Job) -> bool:
    """
    A listing is verified only when an authorised source or direct
    employer evidence confirms BOTH employer identity and this vacancy.
    HTTPS alone is not proof of authenticity.
    """
    return (
        job.employer_verified
        and job.vacancy_confirmed
        and valid_https(job.source_url)
        and valid_https(job.apply_url)
        and bool(job.title.strip())
        and bool(job.company.strip())
    )


def search_jobs(query: str) -> list[Job]:
    """
    Integrate an authorised job-board API/feed or permitted employer
    careers integration here. Keep this empty until a real source is
    connected; do not put sample vacancies in the live response.
    """
    return []
