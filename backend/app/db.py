import os
import logging
from dotenv import load_dotenv
from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

supabase_url = os.environ.get("SUPABASE_URL")
supabase_key = os.environ.get("SUPABASE_SERVICE_KEY")

if not supabase_url or not supabase_key:
    logger.warning("SUPABASE_URL and/or SUPABASE_SERVICE_KEY are not set in the environment variables.")
    # Initialize as None or dummy during startup if env variables are not yet present, 
    # to avoid failing import when starting the app or running offline tests,
    # but raise error when actually attempting to call the client.
    supabase: Client = None
else:
    supabase: Client = create_client(supabase_url, supabase_key)
