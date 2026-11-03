// Example UI add-on (docs/plugins.md): a panel inside 05 SYSTEM and a HELLO view of its own.
// Served as /plugins/hello/ui.js; extra files come from ./ui/ (e.g. /plugins/hello/ui/hello.css).
// Only components from `ui` are used: styling belongs to the theme layer, never to add-on code.
export default function install({ registry, api, ui }) {
  const { h } = ui;
  registry.registerPanel("system", {
    id: "hello",
    order: 900,
    render: (host) => host.append(h("p", {}, "Hello from the example drop-in plugin (examples/plugins/hello/ui.js).")),
  });
  registry.registerView({
    id: "hello",
    order: 200,
    title: "HELLO",
    subtitle: "example add-on",
    mount(root) {
      root.append(h("p", {}, "This view is registered by a plugin. Replace it with your own panels and actions."));
    },
  });
}
