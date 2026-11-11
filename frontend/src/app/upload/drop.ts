/** File types the logger exports come in. Anything else is refused before upload. */
const ACCEPTED = /\.(csv|txt|tsv)$/i;

export function isLoggerExport(f: File): boolean {
  return ACCEPTED.test(f.name);
}

/** True when a drag carries files from the desktop (not text or a link from the page). */
export function dragHasFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes('Files');
}

export interface DropPick {
  file: File | null;
  /** Shown to the user: why nothing was picked, or what was skipped. */
  notice: string | null;
}

/**
 * Pick the one file to upload from a drop. One file per upload, because each file must be
 * matched to its logger. If several are dropped, the first logger export is used.
 */
export function pickDroppedFile(files: ArrayLike<File> | null | undefined): DropPick {
  const all = Array.from(files ?? []);
  if (all.length === 0) return { file: null, notice: null };
  const usable = all.filter(isLoggerExport);
  if (usable.length === 0) {
    const name = all.length === 1 ? all[0].name : `${all.length} files`;
    return {
      file: null,
      notice: `${name} is not a logger export. Drop a .csv, .txt or .tsv file.`,
    };
  }
  if (all.length > 1) {
    return {
      file: usable[0],
      notice: `One file at a time: using ${usable[0].name}. Upload the other ${all.length - 1} next.`,
    };
  }
  return { file: usable[0], notice: null };
}
