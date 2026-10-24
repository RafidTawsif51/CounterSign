// Character alignment between a vendor's real domain and a lookalike, for highlighting what differs.

export interface DiffPart {
  text: string;
  changed: boolean;
}

/** Levenshtein alignment. Returns both strings split into unchanged and changed runs. */
export function diffDomains(real: string, fake: string): { real: DiffPart[]; fake: DiffPart[] } {
  const n = real.length;
  const m = fake.length;
  const d = Array.from({ length: n + 1 }, (_, i) => Array.from({ length: m + 1 }, (_, j) => (i === 0 ? j : j === 0 ? i : 0)));
  for (let i = 1; i <= n; i++)
    for (let j = 1; j <= m; j++)
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (real[i - 1] === fake[j - 1] ? 0 : 1));

  const realMarks: boolean[] = Array(n).fill(false);
  const fakeMarks: boolean[] = Array(m).fill(false);
  let i = n;
  let j = m;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && d[i][j] === d[i - 1][j - 1] + (real[i - 1] === fake[j - 1] ? 0 : 1)) {
      if (real[i - 1] !== fake[j - 1]) realMarks[i - 1] = fakeMarks[j - 1] = true;
      i--;
      j--;
    } else if (i > 0 && d[i][j] === d[i - 1][j] + 1) {
      realMarks[--i] = true; // missing from the lookalike
    } else {
      fakeMarks[--j] = true; // added in the lookalike
    }
  }
  return { real: runs(real, realMarks), fake: runs(fake, fakeMarks) };
}

function runs(text: string, marks: boolean[]): DiffPart[] {
  const out: DiffPart[] = [];
  for (let k = 0; k < text.length; k++) {
    const last = out.at(-1);
    if (last && last.changed === marks[k]) last.text += text[k];
    else out.push({ text: text[k], changed: marks[k] });
  }
  return out;
}

export function domainOf(address: string) {
  return address.split("@").pop()!.toLowerCase();
}
