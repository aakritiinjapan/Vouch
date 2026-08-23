// Helper function to extract currency from price text
function extractCurrency(priceText) {
  if (!priceText) return 'USD'; // fallback
  // Match common currency symbols at the start
  let match = priceText.match(/^([£€$¥₹₽])/);
  if (match) {
    let symbolMap = {
      '$': 'USD',
      '€': 'EUR',
      '£': 'GBP',
      '¥': 'JPY',
      '₹': 'INR',
      '₽': 'RUB'
    };
    return symbolMap[match[1]] || 'USD';
  }
  return 'USD'; // fallback
}

// Helper function to parse price value
function parsePriceValue(priceText) {
  if (!priceText) return null;
  let cleaned = priceText.replace(/[^0-9.,]/g, '');
  // Remove thousand separators (commas) and parse
  let value = parseFloat(cleaned.replace(/,/g, ''));
  return isNaN(value) ? null : value;
}

let products = $('.grid .item').toArray().map(item => {
  let $item = $(item);
  
  // Extract name
  let name = $item.find('.item-title').text_sane();
  
  // Extract current price - the second .money span is the current selling price
  let price_text = $item.find('.item-price .money').eq(1).text_sane();
  let currency = extractCurrency(price_text);
  let price_value = parsePriceValue(price_text);
  let price = price_value !== null ? new Money(price_value, currency) : null;
  
  // Extract original price (may not exist)
  let original_price = null;
  let original_price_text = $item.find('.price-was').text_sane();
  if (original_price_text) {
    let original_price_value = parsePriceValue(original_price_text);
    if (original_price_value !== null) {
      original_price = new Money(original_price_value, currency);
    }
  }
  
  // Extract shipping cost - the first .money span is the shipping cost
  let shipping_text = $item.find('.item-price .money').first().text_sane();
  let shipping_value = parsePriceValue(shipping_text);
  let shipping = shipping_value !== null ? new Money(shipping_value, currency) : null;
  
  // Extract rating
  let rating_text = $item.find('.rating').text_sane();
  let rating = parseFloat(rating_text);
  if (isNaN(rating)) rating = null;
  
  // Extract stock status - check for 'in' class instead of text match
  let stock_element = $item.find('.stock');
  let in_stock = stock_element.hasClass('in');
  
  return {
    name,
    price,
    original_price,
    shipping,
    rating,
    in_stock
  };
});

return { products };