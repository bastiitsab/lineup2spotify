# Spotify Playlist Generator (PKCE)

Creates a Spotify playlist from a Markdown band list by adding the configured number of top tracks per band.

## Prerequisites

- Python 3
- A Spotify Developer app (Client ID + Redirect URI)
- macOS (only for the optional OCR step — uses Swift + Vision framework)

## Spotify Developer Setup

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create (or open) your app
3. Copy your **Client ID**
4. In app settings, add this Redirect URI exactly:
    - `http://127.0.0.1:4202`

## Extract bands from a lineup image (optional)

If you have a festival lineup as an image, you can extract band names via OCR:

```bash
./extract_bands.sh <image> <output.md> "<Heading>"
```

Example:

```bash
./extract_bands.sh kh-heimspiel/2026/lineup.jpeg kh-heimspiel/2026/bands.md "Kärbholz Heimspiel 2026"
```

This creates a Markdown file with one band per line.

> **Note:** The OCR output is raw and will include noise (URLs, dates, venue info, broken words). You need to manually review the file and clean it up — remove non-band lines, merge split names, and fix misspellings — before running the playlist generator.

## Configure `.env`

```bash
cp .env.example .env
```

Edit `.env` (minimal required config):

```env
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_REDIRECT_URI=http://127.0.0.1:4202
BANDS_FILE_PATH=path/to/bands.md
```

Optional overrides (all have defaults):

```env
SPOTIFY_MARKET=DE
NOT_FOUND_HINT_TEXT=_(not added: no exact Spotify artist match)_
SKIPPED_HINT_TEXT=_(not added: intentionally skipped)_
TOP_TRACKS_PER_ARTIST=5
SPOTIFY_SEARCH_LIMIT=5
SPOTIFY_ADD_CHUNK_SIZE=100
SPOTIFY_SCOPES=playlist-modify-private playlist-modify-public
SPOTIFY_TOKEN_CACHE_PATH=.spotify_cache
```

Relative paths are resolved from the script folder, for example:

```env
SPOTIFY_TOKEN_CACHE_PATH=.spotify_cache
```

## Run

```bash
./run_playlist.sh
```

What happens:
- Installs Python dependencies
- Opens Spotify login/consent in your browser (interactive PKCE)
- Derives playlist name from the first `#` heading in `bands.md`
- Removes your existing playlist(s) with that derived playlist name
- Creates a fresh public playlist
- Prints the playlist URL

## Notes

- If a band can’t be matched automatically, it is listed at the end of the script output.
- Track duplicates across artists are removed.
- The configured band list file is updated automatically with hints for:
  - no exact Spotify artist match
  - intentionally skipped bands
- Intentional skip control comes from `bands.md`: add the configured `SKIPPED_HINT_TEXT` to a band line to skip it.
- `.env` and `.spotify_cache` are ignored via `.gitignore` and should not be committed.

## Reuse for other festivals

- Point `BANDS_FILE_PATH` to another markdown list.
- Change the first heading in that markdown file to control playlist name.
- Optionally adjust `SPOTIFY_MARKET` and `TOP_TRACKS_PER_ARTIST`.

## References

- [Spotify PKCE flow](https://developer.spotify.com/documentation/web-api/tutorials/code-pkce-flow)
- [Spotify scopes](https://developer.spotify.com/documentation/web-api/concepts/scopes)
- [Spotipy docs](https://spotipy.readthedocs.io/)

## Disclaimer

This project is not affiliated with, endorsed by, or associated with Spotify AB. "Spotify" is a registered trademark of Spotify AB.

Use this tool at your own risk. The author is not responsible for any misuse, account restrictions, or violations of the [Spotify Developer Terms of Service](https://developer.spotify.com/terms) that may result from using this software. You are solely responsible for complying with Spotify's terms when using their API.

This project is provided "as is", without warranty of any kind. See the [LICENSE](LICENSE) file for details.
