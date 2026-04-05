import { cn } from '@/lib/utils';

interface PageContainerProps {
  children: React.ReactNode;
  className?: string;
}

export default function PageContainer({ children, className }: PageContainerProps) {
  return (
    <div className={cn('max-w-5xl mx-auto px-4 py-6 lg:px-6 lg:py-8', className)}>
      {children}
    </div>
  );
}
