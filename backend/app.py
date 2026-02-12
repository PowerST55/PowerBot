import os
import sys
import traceback


def _in_venv() -> bool:
	return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def _venv_python(venv_dir: str) -> str | None:
	if os.name == "nt":
		candidate = os.path.join(venv_dir, "Scripts", "python.exe")
	else:
		candidate = os.path.join(venv_dir, "bin", "python")
	return candidate if os.path.isfile(candidate) else None


def _reexec_in_venv(venv_dir: str = ".venv") -> None:
	if _in_venv():
		return

	script_dir = os.path.dirname(os.path.abspath(__file__))
	project_dir = os.path.abspath(os.path.join(script_dir, os.pardir))

	candidates = [
		os.path.abspath(venv_dir),
		os.path.join(project_dir, venv_dir),
		os.path.join(script_dir, venv_dir),
	]

	for candidate_dir in candidates:
		venv_python = _venv_python(candidate_dir)
		if venv_python:
			os.execv(venv_python, [venv_python, *sys.argv])

	print("No se encontro el entorno virtual en ninguno de estos paths:")
	for candidate_dir in candidates:
		print(f"- {candidate_dir}")
	print("Ejecutando con el interprete actual.")


def main() -> None:
	# TODO: coloca aqui la logica real de tu app
	print("hola mundo")


if __name__ == "__main__":
	_reexec_in_venv(".venv")
	try:
		main()
	except Exception:
		traceback.print_exc()
		if sys.stdin.isatty():
			input("\nOcurrio un error. Presiona Enter para cerrar...")
		raise
