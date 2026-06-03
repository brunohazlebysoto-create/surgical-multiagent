import subprocess

def get_process_on_port(port):
    try:
        # Run netstat to find process using port
        output = subprocess.check_output("netstat -ano", shell=True).decode('cp850', errors='replace')
        for line in output.splitlines():
            if f":{port} " in line or f"0.0.0.0:{port} " in line or f"127.0.0.1:{port} " in line:
                parts = line.strip().split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    state = parts[-2]
                    print(f"Found connection on port {port}: PID={pid}, State={state}")
                    # Try to get process details via tasklist
                    try:
                        tasklist_out = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True).decode('cp850', errors='replace')
                        print("Process Details:")
                        print(tasklist_out)
                    except Exception as e:
                        print(f"Could not get task details for PID {pid}: {e}")
                    return pid
        print(f"No active connection found on port {port}")
    except Exception as e:
        print(f"Error checking port: {e}")
    return None

get_process_on_port(8000)
