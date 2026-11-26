import { BrandingScreen } from '../../../../components/settings/branding/BrandingScreen';
import { SettingsLayout } from '../../../../components/settings/SettingsLayout';

export default function BrandingPage() {
  return (
    <SettingsLayout active="branding">
      <BrandingScreen />
    </SettingsLayout>
  );
}
