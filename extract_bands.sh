#!/bin/bash
set -euo pipefail

# Extract band names from a festival lineup image using macOS Vision OCR.
# Usage: ./extract_bands.sh <image> <output.md> <heading>
#
# Arguments:
#   image      Path to the lineup image (JPEG, PNG, etc.)
#   output.md  Path to the Markdown file to create
#   heading    First-line heading for the Markdown file (e.g. "Kärbholz Heimspiel 2026")
#
# Requires: macOS (uses Swift + Vision framework)

if [[ $# -ne 3 ]]; then
    echo "Usage: $0 <image> <output.md> <heading>" >&2
    exit 1
fi

IMAGE="$1"
OUTPUT="$2"
HEADING="$3"

if [[ ! -f "$IMAGE" ]]; then
    echo "Error: image not found: $IMAGE" >&2
    exit 1
fi

IMAGE_ABS="$(cd "$(dirname "$IMAGE")" && pwd)/$(basename "$IMAGE")"

SWIFT_SCRIPT=$(mktemp /tmp/ocr_XXXXXX.swift)
trap 'rm -f "$SWIFT_SCRIPT"' EXIT

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

echo "Running OCR on: $IMAGE"
OCR_OUTPUT=$(swift "$SWIFT_SCRIPT" "$IMAGE_ABS")

{
    echo "# $HEADING"
    echo ""
    while IFS= read -r line; do
        trimmed=$(echo "$line" | xargs)
        [[ -n "$trimmed" ]] && echo "- $trimmed"
    done <<< "$OCR_OUTPUT"
} > "$OUTPUT"

LINE_COUNT=$(grep -c '^- ' "$OUTPUT")
echo "Wrote $LINE_COUNT bands to $OUTPUT"
echo ""
echo "Review the file and clean up any OCR artifacts before running the playlist generator."
