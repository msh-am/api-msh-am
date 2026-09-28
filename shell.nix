{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python313
    python313Packages.fastapi
    python313Packages.uvicorn
    python313Packages.paho-mqtt
    python313Packages.meshtastic
    python313Packages.pydantic
    python313Packages.httpx
    python313Packages.cryptography
    python313Packages.pytest
    mosquitto
    sqlite
    curl
  ];

  shellHook = ''
    export PYTHONPATH="$PWD:$PYTHONPATH"
    echo "============================================="
    echo "  Meshtastic Armenia API (api.msh.am) Shell  "
    echo "============================================="
    echo "Run server:  uvicorn src.main:app --reload --port 8000"
    echo "Run tests:   pytest"
  '';
}
