const DEFAULT_MAX_LABEL_LENGTH = 24;


export function compactObjectLabel(
  owner: string,
  name: string,
  maxLength = DEFAULT_MAX_LABEL_LENGTH,
) {
  const fullLabel = `${owner}.${name}`;
  if (fullLabel.length <= maxLength) return fullLabel;

  const minimumNameLength = Math.min(8, Math.max(1, maxLength - 2));
  const maximumOwnerLength = Math.max(1, maxLength - minimumNameLength - 2);
  const compactOwner = owner.length > maximumOwnerLength
    ? `${owner.slice(0, Math.max(1, maximumOwnerLength - 1))}…`
    : owner;
  const nameLength = Math.max(1, maxLength - compactOwner.length - 2);
  return `${compactOwner}.${name.slice(0, nameLength)}…`;
}
