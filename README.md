# Not Everywhere Warms Equally (DSC 106 Project 3)

Interactive D3 map of projected warming from CMIP6 (GFDL-ESM4, near-surface air temperature).

- `prep/download.py`: mirrors the needed CMIP6 zarr stores from the public Google Cloud bucket into `data/raw/` (about 600 MB, resumes on dropped connections)
- `prep/prepare_data.py`: makes the six exploratory graphs in `figures/` and exports `docs/data/warming.json` (5° grid, 5-year means, 3 scenarios, warming vs 1850–1900)
- `docs/`: the D3 page (GitHub Pages serves this folder: Settings → Pages → main branch, /docs)

Run the page locally: `cd docs && python3 -m http.server 8765`, then open http://localhost:8765
