from urllib.parse import urlsplit

from workers import Request, Response, WorkerEntrypoint


class Default(WorkerEntrypoint):
    async def fetch(self, request: Request) -> Response:
        if urlsplit(request.url).path == "/hello":
            return Response("Hello from Workerd!")
        return Response("Not found", status=404)
