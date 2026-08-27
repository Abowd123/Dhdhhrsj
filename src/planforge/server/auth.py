"""
مصادقة برمز مشترك: أضعف ما يُقبل، وأقوى من الصفر.

ليست نظام مستخدمين — رمزٌ واحد يعرفه من يستخدم الأداة. لا صلاحيات ولا
تدقيق ولا إبطال لرمز مسروق إلا بتغييره. تكفي لخادم شخصي، ولا تكفي لأكثر.

`compare_digest` لا `==`: المقارنة العادية تنتهي عند أول حرف مختلف، فزمن
الرد يكشف طول البادئة الصحيحة.
"""
from __future__ import annotations
import os
from hmac import compare_digest
from fastapi import HTTPException, Request

ENV_VAR = "PLANFORGE_TOKEN"
OPEN_PATHS = frozenset({"/", "/api/health"})
"""
الجذر مفتوح كي تُحمَّل صفحة إدخال الرمز. لا تكشف شيئًا: كل مسارات
`/api/*` الأخرى مغلقة، والصفحة فارغة بلا جلسة.
"""


def token() -> str:
    return os.environ.get(ENV_VAR, "").strip()


async def require_token(request: Request) -> None:
    expected = token()
    if not expected:
        raise HTTPException(
            503,
            f"الخادم غير مهيّأ: {ENV_VAR} غير مضبوط",
        )
    if request.url.path in OPEN_PATHS or request.url.path.startswith(
        "/static/"
    ):
        return
    sent = (
        request.headers.get("x-planforge-token", "")
        or request.cookies.get("pf_token", "")
    )
    if not compare_digest(sent, expected):
        raise HTTPException(401, "رمز غير صحيح")
