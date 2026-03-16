#!/bin/bash
cd /home/matheau/code/port_scan && source venv/bin/activate && uvicorn api.main:app --host 0.0.0.0 --port 8001 --reload
