import { Outlet } from 'react-router-dom';
import { Header } from '@/components/Header';
import { Footer } from '@/components/Footer';
import { WhatsAppButton } from '@/components/WhatsAppButton';

export default function PublicLayout() {
  return (
    <>
      <Header />
      <Outlet />
      <Footer />
      <WhatsAppButton />
    </>
  );
}
