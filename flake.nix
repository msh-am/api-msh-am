{
  description = "Meshtastic Armenia Community API (api.msh.am)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python313
            python313Packages.fastapi
            python313Packages.uvicorn
            python313Packages.paho-mqtt
            python313Packages.meshtastic
            python313Packages.pydantic
            python313Packages.httpx
            python313Packages.pytest
            mosquitto
            sqlite
            curl
          ];

          shellHook = ''
            export PYTHONPATH="$PWD:$PYTHONPATH"
          '';
        };
      });
}
