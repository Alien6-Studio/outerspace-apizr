# Apizr API

Run `uv run uvicorn src.app:app --host 127.0.0.1 --port 8000` and open `/docs`.

`POST /process_file/` accepts a multipart `file` ending in `.py` or `.ipynb` and returns an `application/zip` project. The filename cannot contain directory components. Uploads are limited to 10 MiB. Temporary files are isolated per request and removed after the response.

```sh
curl -f -F 'file=@examples/pricing.ipynb' http://127.0.0.1:8000/process_file/ -o pricing-api.zip
```

The API generates code without executing it. It does not accept server-side output directories. The old `/dockerize_file/` endpoint is removed; Docker files are included in the project archive.

Module APIs are mounted at `/code`, `/fastapi`, `/notebook` and `/docker`, with separate `/docs`. This unauthenticated service is intended for local use.
