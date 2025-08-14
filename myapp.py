from quart import Quart
from typing import Optional
from aiomysql import Connection

class MyApp(Quart):
    start_time: float
    db: Optional[Connection]