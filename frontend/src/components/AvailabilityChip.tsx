import { cs } from "../i18n/cs";
import type { Availability } from "../services/api-types";
import { Tag, type TagTone } from "./ui";
import type { IconName } from "./ui";

const TONE: Record<Availability, TagTone> = {
  available: "green",
  not_in_pacs: "red",
  unknown: "amber",
  not_found: "red",
};

const ICON: Record<Availability, IconName> = {
  available: "check",
  not_in_pacs: "close",
  unknown: "question",
  not_found: "close",
};

export default function AvailabilityChip({ availability }: { availability: Availability }) {
  return (
    <Tag tone={TONE[availability]} icon={ICON[availability]}>
      {cs.availability[availability]}
    </Tag>
  );
}
