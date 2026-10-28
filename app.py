
import asyncio
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

app = FastAPI(title="TraceDeck Recon")

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,30}$")
semaphore = asyncio.Semaphore(2)


class SearchRequest(BaseModel):
    username: str = Field(min_length=1, max_length=30)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/search")
async def search(request: SearchRequest):
    username = request.username.strip()

    if not USERNAME_PATTERN.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="Use only letters, numbers, dots, underscores or hyphens."
        )

    async with semaphore:
        try:
            process = await asyncio.create_subprocess_exec(
                "sherlock",
                username,
                "--print-found",
                "--timeout", "10",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )

            try:
                output, _ = await asyncio.wait_for(
                    process.communicate(), timeout=120
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise HTTPException(
                    status_code=504,
                    detail="Search timed out. Try again later."
                )

        except FileNotFoundError:
            raise HTTPException(
                status_code=503,
                detail="Sherlock is not installed on the server."
            )

    lines = output.decode("utf-8", errors="replace").splitlines()
    results = [
        line.strip()[:500]
        for line in lines
        if line.strip() and "http" in line.lower()
    ]

    return {
        "username": username,
        "results": results[:100],
        "return_code": process.returncode
    }


app.mount(
    "/",
    StaticFiles(directory="static", html=True),
    name="static"
)
