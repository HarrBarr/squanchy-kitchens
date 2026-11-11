import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule, MatIconRegistry } from '@angular/material/icon';
import { MatToolbarModule } from '@angular/material/toolbar';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { dragHasFiles } from './upload/drop';
import { UploadLauncher } from './upload/upload-launcher';

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
  host: {
    // A logger file can be dropped anywhere on the app, not only in the upload dialog.
    // preventDefault also stops the browser from navigating away to open the dropped file.
    '(window:dragenter)': 'onWindowDrag($event)',
    '(window:dragover)': 'onWindowDrag($event)',
    '(window:dragleave)': 'onWindowDragLeave($event)',
    '(window:drop)': 'onWindowDrop($event)',
  },
})
export class App {
  private readonly launcher = inject(UploadLauncher);
  /** Full-page "drop to upload" overlay, only while files are dragged over the page. */
  readonly pageDrag = signal(false);

  constructor() {
    // index.html loads the Material Symbols font.
    inject(MatIconRegistry).setDefaultFontSetClass('material-symbols-outlined');
  }

  openUpload(): void {
    this.launcher.open();
  }

  onWindowDrag(e: DragEvent): void {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    // With the dialog open, its own drop zone highlights instead.
    this.pageDrag.set(!this.launcher.isOpen);
  }

  onWindowDragLeave(e: DragEvent): void {
    // relatedTarget is null when the pointer leaves the browser window.
    if (!e.relatedTarget) this.pageDrag.set(false);
  }

  onWindowDrop(e: DragEvent): void {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    this.pageDrag.set(false);
    const files = e.dataTransfer?.files;
    if (files?.length) this.launcher.open(files);
  }
}
