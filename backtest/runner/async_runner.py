import asyncio
import threading
import logging
import errno

logger = logging.getLogger(__name__)


class AsyncRunner:
    """
        负责维护一个全局唯一 单例Event Loop
    """
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._init()
            return cls._instance

    def _init(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="GlobalAsyncLoop", daemon=True)
        self._ready_event = threading.Event()
        self._started = False

    def start(self):
        if not self._started:
            self._thread.start()
            self._ready_event.wait()
            self._started = True
            logger.info("Global AsyncRunner started.")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        
        self._loop.set_exception_handler(self._ignore_errno35) # macos gRPC Error
        
        self._ready_event.set()
        try:
            self._loop.run_forever()
        finally:
            self._loop.close()

    def _ignore_errno35(self, loop, context):
        exc = context.get('exception')
        if isinstance(exc, BlockingIOError) and exc.errno == errno.EAGAIN:
            return
        if "Resource temporarily unavailable" in context.get("message", ""):
            return
        loop.default_exception_handler(context)

    def get_loop(self):
        return self._loop

    def run_sync(self, coro):
        if not self._started:
            self.start()
        
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result()
        except Exception as e:
            logger.error(f"Async call failed: {e}")
            raise e

    def stop(self):
        if self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=1)


# cdef inline tuple init_event_loop():
#     try:
#         loop = asyncio.get_running_loop() # Ray Actor Loop 
#         print(f"Attached to existing Event Loop: {id(loop)}")
#         is_background = False
#     except RuntimeError:
#         loop = asyncio.new_event_loop()
#         if hasattr(loop, 'set_debug'):
#             loop.set_debug(False)
    
#         _loop_thread = threading.Thread(
#             target=_run_event_loop,
#             args=(loop,),
#             daemon=True,
#             name="AsyncClient-EventLoop"
#         )
#         _loop_thread.start()
#         print(f"Started internal background thread.")
#         is_background = True
#     return (loop, is_background)


# cdef inline void _run_event_loop(object loop):
#     asyncio.set_event_loop(loop)
#     try:
#         loop.run_forever()
#     except Exception as e:
#         print(f"Event loop error: {e}")

