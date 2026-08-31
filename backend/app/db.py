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

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

_client: Client | None = None


def get_client() -> Client:
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
            raise RuntimeError(
                "SUPABASE_URL and SUPABASE_SERVICE_KEY must be set (see .env.example). "
                "Create a project at https://supabase.com, run backend/supabase/schema.sql "
                "in its SQL editor, then copy the Project URL and service_role key into your .env."
            )
        _client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    return _client