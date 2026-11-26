// Old address of Ban & Meta Radar (phone alerts link here): it now lives in Market → Meta.
import { Redirect } from 'expo-router';

export default function Meta() {
  return <Redirect href={{ pathname: '/market', params: { tab: 'meta' } }} />;
}
