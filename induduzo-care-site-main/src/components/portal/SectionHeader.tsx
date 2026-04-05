interface SectionHeaderProps {
  title: string;
  description?: string;
}

export default function SectionHeader({ title, description }: SectionHeaderProps) {
  return (
    <div className="mb-6">
      <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">{title}</h1>
      {description && (
        <p className="text-muted-foreground mt-1 text-base">{description}</p>
      )}
    </div>
  );
}
