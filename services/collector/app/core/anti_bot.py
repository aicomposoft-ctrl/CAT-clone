from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AntiBotAssessment:
    is_blocked: bool
    reason: str
    confidence: str


_CHALLENGE_SIGNALS = (
    "captcha",
    "blocked",
    "доступ запрещ",
    "доступ огранич",
    "access denied",
    "are you human",
    "verify you are human",
    "подтвердите, что вы не робот",
    "почти готово",
    "robot",
    "cf-challenge",
    "challenge-platform",
)


def classify_page_state(
    *,
    platform_name: str,
    url: str,
    title: str,
    body: str,
    html: str,
) -> AntiBotAssessment:
    name = (platform_name or "").lower()
    url_l = (url or "").lower()
    title_l = (title or "").lower()
    body_l = (body or "").lower()
    html_l = (html or "").lower()

    if any(sig in title_l or sig in url_l or sig in body_l or sig in html_l for sig in _CHALLENGE_SIGNALS):
        return AntiBotAssessment(True, "challenge_page", "high")

    if (
        "http 401" in title_l or "http 403" in title_l
        or "http 401" in body_l or "http 403" in body_l
        or "error forbidden" in body_l
        or "403 forbidden" in title_l or "401 unauthorized" in title_l
    ):
        return AntiBotAssessment(True, "geo_or_auth_block", "high")

    if "lenta" in name and ("доступ к сайту" in body_l or "forbidden" in body_l):
        return AntiBotAssessment(True, "geo_or_auth_block", "high")

    if "ozon" in name and ("temporary redirect" in body_l or "__rr=1" in url_l):
        return AntiBotAssessment(True, "challenge_page", "medium")

    body_len = len(body.strip())
    html_len = len(html.strip())
    if body_len < 24 and not title_l.strip():
        return AntiBotAssessment(True, "empty_response", "high")

    if "wildberries" in name and body_len < 80:
        return AntiBotAssessment(True, "empty_response", "high")

    if ("самокат" in name or "samocat" in name) and body_len < 80 and html_len < 6000:
        return AntiBotAssessment(True, "empty_response", "high")

    if body_len < 80 and html_len < 2000:
        return AntiBotAssessment(True, "empty_response", "medium")

    return AntiBotAssessment(False, "clear", "low")


def classify_parse_failure(*, body: str, html: str) -> str:
    if len((body or "").strip()) < 80 and len((html or "").strip()) < 3000:
        return "empty_response"
    return "soft_parse_failure"
