"""Analysis server for the Qt application: the app starts it with QProcess and they talk in JSON lines.

Request:   {"id": 3, "cmd": "prepare", "args": {"index": 578}}
Response:  {"id": 3, "ok": true, ...result}  or  {"id": 3, "ok": false, "error": "..."}
Progress:  {"id": 3, "progress": "Calibrando la cámara…"}  (as many as needed before the response)

Commands (see offside_inference/session.py):
    open     {paths: [video, image or folder path, or several images]}
    frame    {index or number, max_width?}  -> {path} JPEG for display
    prepare  {index}                        -> calibration, numbered players and teams
    propose  {index, direction, attacker}   -> proposed second-last defender
    analyze  {index, attacker, defender, direction, ball?} -> decision, viewer JSON and pass image
             ball: "auto" (the detector's, default), "none" (no ball) or [u, v] in video pixels
    quit

On start-up it writes {"event": "ready"}. Anything the libraries print goes to stderr.
"""
import json
import sys
import traceback


def main():
    protocol = sys.stdout
    sys.stdout = sys.stderr  # keep library prints from mixing with the responses

    def send(message):
        protocol.write(json.dumps(message, ensure_ascii=False) + "\n")
        protocol.flush()

    send({"event": "ready"})
    session = None
    try:
        for line in sys.stdin:
            if not line.strip():
                continue
            request = json.loads(line)
            rid, cmd, args = request.get("id"), request.get("cmd"), request.get("args", {})
            if cmd == "quit":
                break
            try:
                if session is None:
                    send({"id": rid, "progress": "Cargando la librería de análisis…"})
                    from offside_inference.session import Session
                    session = Session()

                def progress(message, rid=rid):
                    send({"id": rid, "progress": message})

                if cmd == "open":
                    result = session.open(args["paths"])
                elif cmd == "frame":
                    index = session.index_of(int(args["number"])) if "number" in args else int(args["index"])
                    result = session.frame_image(index, int(args.get("max_width", 1600)))
                elif cmd == "prepare":
                    result = session.prepare(int(args["index"]), progress)
                elif cmd == "propose":
                    result = session.propose(int(args["index"]), int(args["direction"]), int(args["attacker"]))
                elif cmd == "analyze":
                    result = session.analyze(int(args["index"]), int(args["attacker"]), int(args["defender"]),
                                             int(args["direction"]), progress, args.get("ball", "auto"))
                else:
                    raise ValueError(f"Orden desconocida: {cmd}")
                send({"id": rid, "ok": True, **result})
            except Exception as e:  # the server stays alive: the application shows the error
                traceback.print_exc()
                send({"id": rid, "ok": False, "error": str(e) or type(e).__name__})
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
