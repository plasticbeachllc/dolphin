import { Collapsible as CollapsiblePrimitive } from "bits-ui";
import Root from "./collapsible.svelte";

const Trigger = CollapsiblePrimitive.Trigger;
const Content = CollapsiblePrimitive.Content;

export {
  Root,
  Trigger,
  Content,
  //
  Root as Collapsible,
  Trigger as CollapsibleTrigger,
  Content as CollapsibleContent,
};
