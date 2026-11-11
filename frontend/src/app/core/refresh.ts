import { Injectable, signal } from '@angular/core';

/** Bumped after an upload or a registry change so open screens reload their data. */
@Injectable({ providedIn: 'root' })
export class Refresh {
  readonly version = signal(0);
  bump(): void {
    this.version.update((v) => v + 1);
  }
}
