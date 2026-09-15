from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
import json
import os

from logic.llm_utils import choose_agent
from logic.run import WebSocketManager


class ResearchRequest(BaseModel):
    task: str
    report_type: str
    agent: str


app = FastAPI()
app.mount("/site", StaticFiles(directory="frontend"), name="site")
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")


# Dynamic directory for outputs once first research is run
@app.on_event("startup")
def startup_event():
    if not os.path.isdir("outputs"):
        os.makedirs("outputs")
    app.mount("/outputs", StaticFiles(directory="outputs"), name="outputs")


templates = Jinja2Templates(directory="frontend")

manager = WebSocketManager()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def read_root(request: Request):
    return templates.TemplateResponse('index.html', {"request": request, "report": None})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data.startswith("start"):
                json_data = json.loads(data[6:])
                task = json_data.get("task")
                report_type = json_data.get("report_type")
                agent = json_data.get("agent")
                # temporary so "normal agents" can still be used and not just auto generated, will be removed when we move to auto generated
                if agent == "Auto Agent":
                    agent_dict = choose_agent(task)
                    agent = agent_dict.get("agent")
                    agent_role_prompt = agent_dict.get("agent_role_prompt")
                else:
                    agent_role_prompt = None

                await websocket.send_json({"type": "logs", "output": f"Initiated an Agent: {agent}"})
                if task and report_type and agent:
                    try:
                        await manager.start_streaming(
                            task,
                            report_type,
                            agent,
                            agent_role_prompt,
                            websocket,
                        )
                    except WebSocketDisconnect:
                        raise
                    except Exception as exc:
                        error_message = (
                            f"Research run failed: {type(exc).__name__}: {exc}"
                        )
                        print(error_message)
                        await websocket.send_json(
                            {"type": "error", "output": error_message}
                        )
                else:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "output": "Research run failed: missing required parameters.",
                        }
                    )

    except WebSocketDisconnect:
        await manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
