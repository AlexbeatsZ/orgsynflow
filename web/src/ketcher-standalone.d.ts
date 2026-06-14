declare module "ketcher-standalone/dist/binaryWasm" {
  import type { ServiceMode, StructService, StructServiceOptions, StructServiceProvider } from "ketcher-core";

  export class StandaloneStructServiceProvider implements StructServiceProvider {
    mode: ServiceMode;
    createStructService(options: StructServiceOptions): StructService;
  }
}
