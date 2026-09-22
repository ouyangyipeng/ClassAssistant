type Decision = { event: "agree"; buttonId: string } | { event: "disagree" };
type Resolve = (decision: Decision) => void;

export class PrivacyGate {
  private pending = new Set<Resolve>();
  private listeners = new Set<(visible: boolean) => void>();

  constructor() {
    if (typeof wx.onNeedPrivacyAuthorization !== "function") return;
    // Official 5.2.3 typings incorrectly model this callback as GeneralCallbackResult.
    // Its adjacent API documentation specifies a resolve function as the first argument.
    const register = wx.onNeedPrivacyAuthorization as unknown as (
      listener: (resolve: Resolve) => void,
    ) => void;
    register.call(wx, (resolve) => {
      this.pending.add(resolve);
      this.notify();
    });
  }

  subscribe(listener: (visible: boolean) => void): () => void {
    this.listeners.add(listener);
    listener(this.pending.size > 0);
    return () => {
      this.listeners.delete(listener);
    };
  }

  finish(agree: boolean): void {
    const pending = [...this.pending];
    this.pending.clear();
    this.notify();
    for (const resolve of pending)
      resolve(
        agree
          ? { event: "agree", buttonId: "classfox-privacy-agree" }
          : { event: "disagree" },
      );
  }

  private notify(): void {
    for (const listener of this.listeners) listener(this.pending.size > 0);
  }
}
let gate: PrivacyGate | undefined;
export function privacyGate(): PrivacyGate {
  return (gate ??= new PrivacyGate());
}
