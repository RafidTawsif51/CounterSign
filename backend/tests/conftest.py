import os
import tempfile

# Must be set before any app module imports the engine.
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = os.path.join(_tmp, "uploads")
os.environ["EXTRACT_CACHE_DIR"] = os.path.join(_tmp, "extract_cache")
os.environ["FRONTEND_URL"] = "https://countersign.example"
