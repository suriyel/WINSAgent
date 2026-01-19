"""
任务 API 路由
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime

from app.models.schemas import (
    TaskInfo,
    TaskListResponse,
    TaskStatus,
    TodoStep,
    TodoStatus,
)
from app.agents import get_agent_graph

router = APIRouter()

# 内存存储（生产环境应使用数据库）
_tasks_store: dict[str, TaskInfo] = {}


@router.get("/", response_model=TaskListResponse)
async def list_tasks(skip: int = 0, limit: int = 20):
    """获取任务列表"""
    tasks = list(_tasks_store.values())
    tasks.sort(key=lambda x: x.updated_at, reverse=True)

    return TaskListResponse(
        tasks=tasks[skip : skip + limit],
        total=len(tasks),
    )


@router.get("/{task_id}", response_model=TaskInfo)
async def get_task(task_id: str):
    """获取任务详情"""
    if task_id not in _tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    return _tasks_store[task_id]


@router.post("/create", response_model=TaskInfo)
async def create_task(thread_id: str, title: str):
    """创建新任务"""
    import uuid

    task_id = str(uuid.uuid4())
    task = TaskInfo(
        task_id=task_id,
        thread_id=thread_id,
        title=title,
        status=TaskStatus.PENDING,
        progress=0,
        todo_list=[],
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )

    _tasks_store[task_id] = task
    return task


@router.put("/{task_id}/status")
async def update_task_status(task_id: str, status: TaskStatus):
    """更新任务状态"""
    if task_id not in _tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _tasks_store[task_id]
    task.status = status
    task.updated_at = datetime.now()

    return {"message": "状态更新成功", "task_id": task_id, "status": status}


@router.delete("/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    if task_id not in _tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    del _tasks_store[task_id]
    return {"message": "任务删除成功", "task_id": task_id}


@router.get("/{task_id}/steps", response_model=list[TodoStep])
async def get_task_steps(task_id: str):
    """获取任务步骤列表"""
    if task_id not in _tasks_store:
        raise HTTPException(status_code=404, detail="任务不存在")

    return _tasks_store[task_id].todo_list


def sync_task_from_thread(thread_id: str) -> TaskInfo | None:
    """从会话状态同步任务信息"""
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        state = graph.get_state(config)
        if not state or not state.values:
            return None

        values = state.values

        # 查找或创建任务
        task = None
        for t in _tasks_store.values():
            if t.thread_id == thread_id:
                task = t
                break

        if not task:
            import uuid

            task = TaskInfo(
                task_id=str(uuid.uuid4()),
                thread_id=thread_id,
                title=values.get("parsed_intent", "新任务")[:50],
                status=TaskStatus.PENDING,
                progress=0,
                todo_list=[],
            )
            _tasks_store[task.task_id] = task

        # 同步状态
        status_map = {
            "pending": TaskStatus.PENDING,
            "running": TaskStatus.RUNNING,
            "success": TaskStatus.SUCCESS,
            "failed": TaskStatus.FAILED,
            "waiting_input": TaskStatus.WAITING_INPUT,
        }
        task.status = status_map.get(
            values.get("final_status", "pending"), TaskStatus.PENDING
        )

        # 同步步骤
        todo_list = []
        for step in values.get("todo_list", []):
            todo_list.append(
                TodoStep(
                    id=step["id"],
                    description=step["description"],
                    tool_name=step.get("tool_name"),
                    status=TodoStatus(step["status"]),
                    result=step.get("result"),
                    error=step.get("error"),
                    depends_on=step.get("depends_on", []),
                    progress=step.get("progress", 0),
                )
            )
        task.todo_list = todo_list

        # 计算进度
        if todo_list:
            completed = sum(1 for s in todo_list if s.status == TodoStatus.COMPLETED)
            task.progress = int(completed / len(todo_list) * 100)

        task.updated_at = datetime.now()

        return task

    except Exception:
        return None
