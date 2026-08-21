def make_stdout_handler(window):
    def handler():
        raw = window.process.readAllStandardOutput().data()
        data = bytes(raw).decode("utf-8", errors="replace")

        if hasattr(window, 'log'):
            window.log(data)
        elif hasattr(window, 'log_view'):
            window.log_view.append(data)
        
        if hasattr(window, 'parse_residuals'):
            window.parse_residuals(data)
            
    return handler


def make_stderr_handler(window):
    def handler():
        raw = window.process.readAllStandardError().data()
        data = bytes(raw).decode("utf-8", errors="replace")
        if hasattr(window, 'log'):
            window.log(f"[ERR] {data}")
        elif hasattr(window, 'log_view'):
            window.log_view.append(f"[ERR] {data}")
    return handler


def make_finished_handler(window):
    def handler():
        if hasattr(window, '_handle_process_finished_log'):
            window._handle_process_finished_log()
        elif hasattr(window, 'log'):
            window.log("\nProcesso finalizado.\n")
        elif hasattr(window, 'log_view'):
            window.log_view.append("\nProcesso finalizado.\n")
    return handler
