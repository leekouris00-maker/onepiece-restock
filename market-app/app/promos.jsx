// Old address of Promos & prize events: it now lives in Market → Promos.
import { Redirect } from 'expo-router';

export default function Promos() {
  return <Redirect href={{ pathname: '/market', params: { tab: 'promos' } }} />;
}
