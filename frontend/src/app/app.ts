import { Component, computed, effect, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule, MatIconRegistry } from '@angular/material/icon';
import { MatMenuModule } from '@angular/material/menu';
import { MatToolbarModule } from '@angular/material/toolbar';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, map } from 'rxjs';
import { Api } from './core/api';
import { Auth } from './core/auth';
import { Refresh } from './core/refresh';
import { Viewport } from './core/viewport';
import { dragHasFiles } from './upload/drop';
import { UploadLauncher } from './upload/upload-launcher';

const PENDING_POLL_MS = 60_000;

@Component({
  selector: 'app-root',
  imports: [
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatToolbarModule,
    MatButtonModule,
    MatIconModule,
    MatMenuModule,
    MatBadgeModule,
    MatDividerModule,
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
  private readonly api = inject(Api);
  private readonly refresh = inject(Refresh);
  readonly auth = inject(Auth);
  /** Puts the `mobileBreakpoint` class on <body> on phone-sized screens. */
  protected readonly viewport = inject(Viewport);
  /** Full-page "drop to upload" overlay, only while files are dragged over the page. */
  readonly pageDrag = signal(false);
  /** Uploads flagged "by mistake" waiting for Summer (admin only). */
  readonly pending = signal(0);

  private readonly url = toSignal(
    inject(Router).events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map((e) => (e as NavigationEnd).urlAfterRedirects),
    ),
    { initialValue: '' },
  );
  /** The app chrome (nav, upload) only for a signed-in user who may use the app. */
  readonly chrome = computed(
    () =>
      !!this.auth.user() &&
      !this.auth.user()!.must_change_password &&
      !this.url().startsWith('/login'),
  );

  constructor() {
    // index.html loads the Material Symbols font.
    inject(MatIconRegistry).setDefaultFontSetClass('material-symbols-outlined');

    // Pending-review badge: on sign-in, after any change, on navigation, and every minute.
    effect((onCleanup) => {
      this.refresh.version();
      this.url();
      if (!this.auth.isAdmin() || !this.chrome()) {
        this.pending.set(0);
        return;
      }
      const load = () =>
        this.api.pendingReviewCount().subscribe({
          next: (n) => this.pending.set(n),
          error: () => undefined,
        });
      load();
      const timer = setInterval(load, PENDING_POLL_MS);
      onCleanup(() => clearInterval(timer));
    });
  }

  openUpload(): void {
    this.launcher.open();
  }

  onWindowDrag(e: DragEvent): void {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy';
    // With the dialog open, its own drop zone highlights instead; signed out, nothing.
    this.pageDrag.set(this.chrome() && !this.launcher.isOpen);
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
    if (files?.length && this.chrome()) this.launcher.open(files);
  }
}
