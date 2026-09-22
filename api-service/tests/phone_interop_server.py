"""Owned loopback fixture for the TypeScript phone client's integration test."""

import asyncio
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from classfox.app import create_app
from classfox.config import RuntimeConfig
from classfox.phone_gateway import PhoneGateway
from tests.test_audio_runtime import NoCredentials


async def main() -> None:
    with TemporaryDirectory(prefix="classfox-phone-interop-") as directory:
        app = create_app(RuntimeConfig(data_dir=Path(directory)), credentials=NoCredentials())
        async with app.router.lifespan_context(app):
            gateway: PhoneGateway = app.state.phone_gateway
            await gateway.start("127.0.0.1", allow_loopback=True)
            # The test transport redirects this synthetic private address to its owned loopback port.
            offer = await gateway.offer()
            offer["address"] = "192.168.42.1"
            print(json.dumps(offer), flush=True)
            while line := await asyncio.to_thread(sys.stdin.readline):
                if line.strip() == "approve":
                    pending = gateway.pairings.status()[0]
                    gateway.pairings.approve(str(pending["id"]), str(pending["client_nonce"]))
                    print(json.dumps({"approved": True, "code": pending["verification_code"]}), flush=True)
                elif line.strip() == "revoke":
                    await gateway.pairings.revoke(str(offer["id"]))
                    print(json.dumps({"revoked": True}), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
