import asyncio

import pytest

from speech_api.errors import ApiError
from speech_api.scheduler import EngineScheduler

pytestmark = pytest.mark.anyio


async def _flood(sched, n_pipe, n_ext):
    order: list[str] = []
    gate = asyncio.Event()

    async def blocker():
        await gate.wait()

    async def job(tag):
        await asyncio.sleep(0)
        order.append(tag)

    first = asyncio.create_task(sched.submit(blocker, pipeline=True))
    await asyncio.sleep(0.01)
    tasks = [asyncio.create_task(sched.submit(lambda: job("P"), pipeline=True)) for _ in range(n_pipe)]
    tasks += [asyncio.create_task(sched.submit(lambda: job("E"), pipeline=False)) for _ in range(n_ext)]
    await asyncio.sleep(0.01)
    gate.set()
    await asyncio.gather(first, *tasks)
    return order


async def test_scheduler_fairness():
    sched = EngineScheduler("omnivoice", concurrency=1, max_waiting=32)
    order = await _flood(sched, 30, 6)
    assert order.count("E") == 6 and order.count("P") == 30
    last_e = max(i for i, t in enumerate(order) if t == "E")
    # while externals are waiting, every 3 consecutive completions include at least one external
    for i in range(0, last_e - 1):
        assert "E" in order[i:i + 3], (i, order)


async def test_pipeline_first_when_no_external():
    sched = EngineScheduler("kokoro", concurrency=1)
    order = await _flood(sched, 5, 0)
    assert order == ["P"] * 5


async def test_externals_alone_all_run():
    sched = EngineScheduler("kokoro", concurrency=1)
    order = await _flood(sched, 0, 4)
    assert order == ["E"] * 4


async def test_queue_full_429():
    sched = EngineScheduler("asr", concurrency=1, max_waiting=2)
    gate = asyncio.Event()

    async def blocker():
        await gate.wait()

    running = asyncio.create_task(sched.submit(blocker, pipeline=False))
    await asyncio.sleep(0.01)
    waiting = [asyncio.create_task(sched.submit(blocker, pipeline=False)) for _ in range(2)]
    await asyncio.sleep(0.01)
    with pytest.raises(ApiError) as e:
        await sched.submit(blocker, pipeline=False)
    assert e.value.status == 429
    assert e.value.headers["Retry-After"] == "10"
    # pipeline calls are not turned away by the external cap
    pipe = asyncio.create_task(sched.submit(blocker, pipeline=True))
    await asyncio.sleep(0.01)
    assert not pipe.done()
    gate.set()
    await asyncio.gather(running, pipe, *waiting)


async def test_failed_call_releases_slot():
    sched = EngineScheduler("asr", concurrency=1)

    async def boom():
        raise RuntimeError("x")

    with pytest.raises(RuntimeError):
        await sched.submit(boom, pipeline=False)

    async def ok():
        return 5

    assert await asyncio.wait_for(sched.submit(ok, pipeline=False), 1) == 5


async def test_cancelled_waiter_is_removed():
    sched = EngineScheduler("asr", concurrency=1, max_waiting=1)
    gate = asyncio.Event()

    async def blocker():
        await gate.wait()

    running = asyncio.create_task(sched.submit(blocker, pipeline=False))
    await asyncio.sleep(0.01)
    w = asyncio.create_task(sched.submit(blocker, pipeline=False))
    await asyncio.sleep(0.01)
    w.cancel()
    await asyncio.sleep(0.01)
    assert sched.waiting == 0
    gate.set()
    await running
