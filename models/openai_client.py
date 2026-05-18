import os

from dotenv import load_dotenv
from openai import OpenAI
from openai._client import OpenAI

load_dotenv()

default_openai_client: OpenAI = OpenAI(base_url=os.getenv("OPENAI_BASE_URL"))