import { copyToClipboard } from '../lib/clipboard';
import { Button } from './ui/button';
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger, DropdownMenuSeparator } from './ui/dropdown-menu';
import { Share2, Copy, Mail, MessageCircle, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';

/**
 * Einheitliche Share-Komponente für Terminplanungen, Umfragen und Links.
 * Props:
 *  - url: string (der zu teilende Link)
 *  - title: string (Titel für die Nachricht)
 *  - description?: string (optionale Beschreibung)
 *  - type?: 'terminplanung' | 'umfrage' | 'buchung' | 'meeting'
 */
export default function ShareMenu({ url, title, description = '', type = 'terminplanung' }) {
  const typeLabel = {
    terminplanung: 'Terminabstimmung',
    umfrage: 'Umfrage',
    buchung: 'Buchung',
    meeting: 'Meeting',
  }[type] || type;

  const copyLink = () => {
    copyToClipboard(url);
    setTimeout(() => toast.success('Link kopiert'), 50);
  };

  const shareWhatsApp = () => {
    const text = `${typeLabel}: ${title}\n${description ? description + '\n' : ''}Hier abstimmen: ${url}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, '_blank');
  };

  const shareEmail = () => {
    const subject = `${typeLabel}: ${title}`;
    const body = `Hallo,\n\nich lade dich zur folgenden ${typeLabel} ein:\n\n${title}${description ? '\n' + description : ''}\n\nHier teilnehmen: ${url}\n\nVielen Dank!`;
    window.open(`mailto:?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`);
  };

  const openLink = () => {
    window.open(url, '_blank');
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="sm" variant="outline" className="rounded-full border-[#E2E4E0] text-xs gap-1.5" data-testid="share-menu-trigger">
          <Share2 className="w-3.5 h-3.5" /> Teilen
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-[200px]">
        <DropdownMenuItem onClick={copyLink} data-testid="share-copy-link">
          <Copy className="w-3.5 h-3.5 mr-2" /> Link kopieren
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={shareWhatsApp} data-testid="share-whatsapp">
          <MessageCircle className="w-3.5 h-3.5 mr-2 text-[#25D366]" /> Per WhatsApp teilen
        </DropdownMenuItem>
        <DropdownMenuItem onClick={shareEmail} data-testid="share-email">
          <Mail className="w-3.5 h-3.5 mr-2 text-[#4A5D4E]" /> Per E-Mail teilen
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={openLink} data-testid="share-open">
          <ExternalLink className="w-3.5 h-3.5 mr-2" /> Im Browser oeffnen
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
