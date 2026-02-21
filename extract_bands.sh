#!/bin/bash
set -euo pipefail

# Extract band names from festival lineup image(s) using macOS Vision OCR.
# Usage: ./extract_bands.sh <output.md> "<Heading>" <image1> [image2 ...]
#
# Arguments:
#   output.md  Path to the Markdown file to create
#   heading    First-line heading for the Markdown file (e.g. "Kärbholz Heimspiel 2026")
#   image(s)   One or more lineup images (JPEG, PNG, etc.)
#
# Requires: macOS (uses Swift + Vision framework)

if [[ $# -lt 3 ]]; then
    echo "Usage: $0 <output.md> \"<Heading>\" <image1> [image2 ...]" >&2
    exit 1
fi

OUTPUT="$1"
HEADING="$2"
shift 2

for img in "$@"; do
    if [[ ! -f "$img" ]]; then
        echo "Error: image not found: $img" >&2
        exit 1
    fi
done

SWIFT_SCRIPT=$(mktemp /tmp/ocr_XXXXXX.swift)
OCR_TEMP=$(mktemp /tmp/ocr_out_XXXXXX.txt)
trap 'rm -f "$SWIFT_SCRIPT" "$OCR_TEMP"' EXIT

cat > "$SWIFT_SCRIPT" <<'SWIFT'
import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
let url = URL(fileURLWithPath: path)

guard let image = NSImage(contentsOf: url) else {
    fputs("Error: cannot load image: \(path)\n", stderr)
    exit(1)
}
var rect = NSRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &rect, context: nil, hints: nil) else {
    fputs("Error: cannot create CGImage\n", stderr)
    exit(1)
}
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["de-DE", "en-US"]
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try handler.perform([request])
for line in (request.results ?? []).compactMap({ $0.topCandidates(1).first?.string }) {
    print(line)
}
SWIFT

for img in "$@"; do
    IMAGE_ABS="$(cd "$(dirname "$img")" && pwd)/$(basename "$img")"
    echo "Running OCR on: $img"
    swift "$SWIFT_SCRIPT" "$IMAGE_ABS" >> "$OCR_TEMP"
done

{
    echo "# $HEADING"
    echo ""
    while IFS= read -r line; do
        trimmed=$(echo "$line" | xargs)
        [[ -n "$trimmed" ]] && echo "- $trimmed"
    done < "$OCR_TEMP"
} > "$OUTPUT"

LINE_COUNT=$(grep -c '^- ' "$OUTPUT" || true)
echo "Wrote $LINE_COUNT lines to $OUTPUT"
echo ""
echo "Review the file and clean up any OCR artifacts before running the playlist generator."
