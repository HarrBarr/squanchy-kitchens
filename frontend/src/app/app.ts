import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule, MatIconRegistry } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { Refresh } from './core/refresh';
import { UploadDialog } from './upload/upload-dialog';

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly dialog = inject(MatDialog);
  private readonly refresh = inject(Refresh);

  constructor() {
    // index.html loads the Material Symbols font.
    inject(MatIconRegistry).setDefaultFontSetClass('material-symbols-outlined');
  }

  openUpload(): void {
    this.dialog
      .open(UploadDialog, { width: '560px', maxWidth: '95vw', autoFocus: false })
      .afterClosed()
      .subscribe((changed) => {
        if (changed) this.refresh.bump();
      });
  }
}
