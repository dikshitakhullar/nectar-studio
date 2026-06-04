/**
 * Dimension formatting + parsing helpers.
 *
 * v1.0.1 — Indian residential designers think in feet. Architects label DXF
 * dimensions like `13'-0" x 12'-4½"`. The lighting-engine API uses meters
 * everywhere; this module is the single bridge between meter-canonical storage
 * and feet-fluent UI labels.
 *
 * Display rule: meters primary (1 dp), feet-inches in parentheses.
 *
 *   formatDim(4.2)  → "4.2m (13'-9½\")"
 *   formatArea(21.4) → "21.4 m² (230 ft²)"
 *
 * Inches are rounded to the nearest half (¼ is finer than designers care about
 * at room scale); the half-inch is rendered as the typographic ½ glyph.
 */

const M_TO_FT = 3.28084;
const SQM_TO_SQFT = 10.7639;
const INCH_FRACTION_PRECISION = 0.5; // round inches to nearest half

/** "4.2m (13'-9½\")" — meters primary, feet-inches in parentheses. */
export function formatDim(meters: number): string {
  if (!Number.isFinite(meters)) return "—";
  const meterPart = formatMeters(meters);
  const feetPart = formatFeetInches(meters);
  return `${meterPart} (${feetPart})`;
}

/** "21.4 m² (230 ft²)" */
export function formatArea(sqm: number): string {
  if (!Number.isFinite(sqm)) return "—";
  const sqft = Math.round(sqm * SQM_TO_SQFT);
  return `${sqm.toFixed(1)} m² (${sqft} ft²)`;
}

/**
 * Parse a dimension string into meters.
 *
 * Accepts:
 *   - `"3.8m"`, `"3.8 m"`     → 3.8
 *   - `"3.8"`                  → 3.8 (bare number assumed meters)
 *   - `"12'-6\""`, `"12'-6"`   → 3.81
 *   - `"12.5'"`, `"12.5 ft"`   → 3.81
 *   - `"12'-6½\""`             → 3.81 (½ + ¼ + ¾ glyphs accepted)
 *
 * Returns `null` for unparseable input so callers can show an error state.
 */
export function parseDim(input: string): number | null {
  if (typeof input !== "string") return null;
  const raw = input.trim();
  if (raw.length === 0) return null;

  // Normalize unicode fractions and quote glyphs.
  const normalized = raw
    .replace(/½/g, ".5")
    .replace(/¼/g, ".25")
    .replace(/¾/g, ".75")
    .replace(/[‘’]/g, "'")
    .replace(/[“”]/g, '"');

  // Meters: "3.8m", "3.8 m", "3.8 meters"
  const mMatch = normalized.match(/^([+-]?\d+(?:\.\d+)?)\s*m(?:eters?)?$/i);
  if (mMatch) {
    const value = Number(mMatch[1]);
    return Number.isFinite(value) ? value : null;
  }

  // Feet + inches: "12'-6", "12'-6\"", "12' 6\"", "12'6"
  const ftInMatch = normalized.match(
    /^([+-]?\d+(?:\.\d+)?)\s*'\s*[-\s]?\s*(\d+(?:\.\d+)?)\s*"?$/,
  );
  if (ftInMatch) {
    const ft = Number(ftInMatch[1]);
    const inches = Number(ftInMatch[2]);
    if (!Number.isFinite(ft) || !Number.isFinite(inches)) return null;
    return (ft + inches / 12) / M_TO_FT;
  }

  // Feet only: "12.5'", "12.5 ft", "12.5 feet"
  const ftMatch = normalized.match(
    /^([+-]?\d+(?:\.\d+)?)\s*(?:'|ft|feet)$/i,
  );
  if (ftMatch) {
    const ft = Number(ftMatch[1]);
    return Number.isFinite(ft) ? ft / M_TO_FT : null;
  }

  // Bare number — assume meters.
  const bareMatch = normalized.match(/^([+-]?\d+(?:\.\d+)?)$/);
  if (bareMatch) {
    const value = Number(bareMatch[1]);
    return Number.isFinite(value) ? value : null;
  }

  return null;
}

// ---------- internals ----------

function formatMeters(meters: number): string {
  // 0 stays "0m"; everything else gets a single decimal.
  if (meters === 0) return "0m";
  return `${meters.toFixed(1)}m`;
}

function formatFeetInches(meters: number): string {
  const totalFt = meters * M_TO_FT;
  let ft = Math.floor(totalFt);
  let inches = (totalFt - ft) * 12;

  // Round inches to nearest half-inch.
  inches = Math.round(inches / INCH_FRACTION_PRECISION) * INCH_FRACTION_PRECISION;

  // Carry on 12-inch overflow (e.g. 11.5" + 0.5 round = 12" → bump foot).
  if (inches >= 12) {
    ft += 1;
    inches -= 12;
  }

  return `${ft}'-${formatInchValue(inches)}"`;
}

function formatInchValue(inches: number): string {
  const whole = Math.floor(inches);
  const frac = inches - whole;
  if (frac === 0) return `${whole}`;
  // Half-inch precision means frac is only ever 0 or 0.5 at this point.
  return `${whole}½`;
}
