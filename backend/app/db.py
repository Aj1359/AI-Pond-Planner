"""
Supabase client setup. Requires SUPABASE_URL and SUPABASE_SERVICE_KEY
environment variables (see backend/.env.example).

The service_role key is used because this client runs entirely
server-side inside the FastAPI backend and needs full read/write access
to every table. Never ship the service_role key to a browser/frontend —
if you ever call Supabase directly from the frontend, use the anon key
plus Row Level Security policies instead.
"""
from __future__ import annotations

import os

try:
    from supabase import create_client, Client
except Exception:
    create_client, Client = None, None

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

_client = None


def get_client():
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY or not create_client:
            return None
        try:
            _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
        except Exception:
            return None
    return _client