// The contract fixture's system: everything is kept in memory, so the core steps can be checked without an application.
import type { BrowserContextOptions } from '@playwright/test';
import { ExpectedMissing } from './errors';

type Row = Record<string, unknown>;

export interface Login {
  storageState?: BrowserContextOptions['storageState'];
  headers?: Record<string, string>;
}

export class System {
  private readonly stored = new Map<string, Row[]>();
  private readonly events = new Map<string, unknown[]>();
  private readonly flags = new Map<string, boolean>();
  private readonly signedIn: Row[] = [];
  private readonly jobsRun: Row[] = [];
  private readonly times: string[] = [];

  baseUrl(): string {
    throw new ExpectedMissing('a running application to open pages of (System.baseUrl)');
  }

  async seed(entity: string, rows: Row[]): Promise<void> {
    this.stored.set(entity, [...(this.stored.get(entity) ?? []), ...rows]);
  }

  async authenticate(actor: string, role: string): Promise<Login> {
    this.signedIn.push({ actor, role });
    return { headers: { 'x-role': role } };
  }

  async setFlag(flag: string, enabled: boolean): Promise<void> {
    this.flags.set(flag, enabled);
  }

  async setTime(moment: Date): Promise<void> {
    this.times.push(moment.toISOString());
  }

  async deliverEvent(event: string, payload: unknown): Promise<void> {
    this.events.set(event, [...(this.events.get(event) ?? []), payload]);
    if (event === 'order placed') {
      const order = payload as Row;
      this.stored.set('order', [...(this.stored.get('order') ?? []), { id: order.id, status: 'placed' }]);
    }
  }

  async runJob(job: string): Promise<void> {
    this.jobsRun.push({ job });
    if (job === 'nightly') {
      this.stored.set('order', (this.stored.get('order') ?? []).map((order) => ({ ...order, status: 'archived' })));
      this.events.set('orders archived', [...(this.events.get('orders archived') ?? []), { count: (this.stored.get('order') ?? []).length }]);
    }
  }

  async records(entity: string): Promise<Row[]> {
    const own: Record<string, Row[]> = {
      login: this.signedIn,
      job: this.jobsRun,
      flag: [...this.flags].map(([flag, enabled]) => ({ flag, enabled })),
      time: this.times.map((time) => ({ time })),
    };
    return own[entity] ?? this.stored.get(entity) ?? [];
  }

  async published(event: string): Promise<unknown[]> {
    return this.events.get(event) ?? [];
  }

  async reset(): Promise<void> {
    this.stored.clear();
    this.events.clear();
  }
}
