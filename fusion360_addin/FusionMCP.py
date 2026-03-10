import sys
import os

_here = os.path.dirname(os.path.abspath(__file__))
# 确保将父目录加入 sys.path，便于按包名导入 fusion360_addin
_parent = os.path.dirname(_here)
if _parent not in sys.path:
    sys.path.insert(0, _parent)


def run(context):
    try:
        from fusion360_addin import run as app_run
        app_run.run(context)
    except Exception as e:
        import traceback
        print("Add-in run failed:", e)
        print(traceback.format_exc())


def stop(context):
    try:
        from fusion360_addin import run as app_run
        app_run.stop(context)
    except Exception as e:
        import traceback
        print("Add-in stop failed:", e)
        print(traceback.format_exc())


