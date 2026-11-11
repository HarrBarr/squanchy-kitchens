import { Injectable, inject } from '@angular/core';
import { MatDialog, MatDialogRef } from '@angular/material/dialog';
import { Refresh } from '../core/refresh';
import { UploadDialog, UploadDialogData } from './upload-dialog';

/** Opens the upload dialog: from the toolbar button, an empty state, or a file dropped
 *  anywhere on the page. A drop while the dialog is open goes into that dialog. */
@Injectable({ providedIn: 'root' })
export class UploadLauncher {
  private readonly dialog = inject(MatDialog);
  private readonly refresh = inject(Refresh);
  private ref: MatDialogRef<UploadDialog, boolean> | null = null;

  get isOpen(): boolean {
    return this.ref !== null;
  }

  open(files?: ArrayLike<File> | null): void {
    if (this.ref) {
      if (files) this.ref.componentInstance.acceptFiles(files);
      return;
    }
    const data: UploadDialogData = { files: files ?? null };
    this.ref = this.dialog.open<UploadDialog, UploadDialogData, boolean>(UploadDialog, {
      width: '560px',
      maxWidth: '95vw',
      autoFocus: false,
      data,
    });
    this.ref.afterClosed().subscribe((changed) => {
      this.ref = null;
      if (changed) this.refresh.bump();
    });
  }
}
